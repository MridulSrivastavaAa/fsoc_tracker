"""
src/fsoc/vision/optical_flow.py
===============================
Local Sparse Lucas-Kanade Optical Flow Estimator for FSOC Optical Tracking.

Features:
- Pyramidal Lucas-Kanade with sub-pixel precision
- Local adaptive ROI focused on predicted beacon position
- Forward-backward (FB) consistency validation and error rejection
- Robust median/trimmed inlier clustering
- Integrated pan-tilt camera motion compensation
- Strict confidence metric and zero-velocity fallback prevention
"""
from __future__ import annotations
import math
from typing import Optional
import cv2
import numpy as np

from ..core.types import FlowResult
from ..core.config import OpticalFlowConfig, AppConfig


class OpticalFlowTracker:
    """
    Local sparse Lucas-Kanade optical flow estimator.
    Tracks beacon motion between successive camera frames.
    """
    def __init__(
        self,
        cfg: OpticalFlowConfig | AppConfig | None = None,
        dt: float = 1.0 / 30.0,
    ) -> None:
        if cfg is None:
            o_cfg = OpticalFlowConfig()
        elif isinstance(cfg, AppConfig):
            o_cfg = cfg.vision.optical_flow
            dt = cfg.pipeline.dt
        elif isinstance(cfg, OpticalFlowConfig):
            o_cfg = cfg
        else:
            raise TypeError(f"Unsupported config type: {type(cfg)}")

        self.cfg = o_cfg
        self.dt = float(dt)

        # Pyramidal LK parameters
        self.lk_params = dict(
            winSize=(self.cfg.win_size, self.cfg.win_size),
            maxLevel=self.cfg.max_pyramid_level,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
            flags=0,
            minEigThreshold=1e-4,
        )

        # Cache for previous frame state
        self.prev_img: Optional[np.ndarray] = None
        self.prev_pos: Optional[tuple[float, float]] = None
        self.prev_pan_deg: float = 0.0
        self.prev_tilt_deg: float = 0.0

    def reset(self) -> None:
        """Reset cached frame state."""
        self.prev_img = None
        self.prev_pos = None
        self.prev_pan_deg = 0.0
        self.prev_tilt_deg = 0.0

    def estimate_flow(
        self,
        curr_img: np.ndarray,
        curr_pan_deg: float = 0.0,
        curr_tilt_deg: float = 0.0,
        hint_pos: Optional[tuple[float, float]] = None,
        px_per_deg_x: float = 160.0,
        px_per_deg_y: float = 160.0,
    ) -> FlowResult:
        """
        Estimate optical flow displacement between previous frame and current frame.

        Args:
            curr_img: Grayscale uint8 viewport frame (480, 640).
            curr_pan_deg: Current camera pan angle in degrees.
            curr_tilt_deg: Current camera tilt angle in degrees.
            hint_pos: Predicted or last-known target position (x, y) in viewport px.
            px_per_deg_x: Camera angular scale X (px/deg).
            px_per_deg_y: Camera angular scale Y (px/deg).

        Returns:
            FlowResult with valid flag, displacements, velocities, and confidence.
        """
        if not self.cfg.enabled:
            return FlowResult(valid=False)

        # If previous frame does not exist, initialize cache and return invalid
        if self.prev_img is None or self.prev_pos is None:
            self.prev_img = curr_img.copy()
            self.prev_pos = hint_pos
            self.prev_pan_deg = curr_pan_deg
            self.prev_tilt_deg = curr_tilt_deg
            return FlowResult(valid=False)

        ref_pos = hint_pos if hint_pos is not None else self.prev_pos
        px, py = ref_pos

        # Camera motion between frame k-1 and frame k
        d_pan = curr_pan_deg - self.prev_pan_deg
        d_tilt = curr_tilt_deg - self.prev_tilt_deg
        cam_dx = float(d_pan * px_per_deg_x)
        cam_dy = float(d_tilt * px_per_deg_y)

        # 1. Define Local ROI around target location
        h, w = curr_img.shape[:2]
        r_half = self.cfg.roi_size_px // 2
        x_min = max(0, int(round(px - r_half)))
        x_max = min(w, int(round(px + r_half)))
        y_min = max(0, int(round(py - r_half)))
        y_max = min(h, int(round(py + r_half)))

        if (x_max - x_min) < 10 or (y_max - y_min) < 10:
            self._update_cache(curr_img, ref_pos, curr_pan_deg, curr_tilt_deg)
            return FlowResult(valid=False, cam_dx=cam_dx, cam_dy=cam_dy)

        # 2. Extract Feature Points within Local ROI
        roi_prev = self.prev_img[y_min:y_max, x_min:x_max]

        # Always include the target sub-pixel centroid
        p_center = np.array([[[float(px), float(py)]]], dtype=np.float32)

        # Fast Shi-Tomasi corner detection on cropped ROI slice
        corners = cv2.goodFeaturesToTrack(
            roi_prev,
            maxCorners=self.cfg.max_corners,
            qualityLevel=self.cfg.quality_level,
            minDistance=self.cfg.min_distance,
        )

        if corners is not None and len(corners) > 0:
            # Offset corners from ROI-local coordinates to viewport coordinates
            corners[:, 0, 0] += float(x_min)
            corners[:, 0, 1] += float(y_min)
            p0 = np.vstack([p_center, corners]).astype(np.float32)
        else:
            # Synthetic local star pattern around centroid if smooth blob
            p0 = np.array([
                [[px, py]],
                [[px - 3.0, py]],
                [[px + 3.0, py]],
                [[px, py - 3.0]],
                [[px, py + 3.0]],
            ], dtype=np.float32)

        # 3. Forward Pyramidal Lucas-Kanade (prev -> curr)
        try:
            p1, st_fwd, err_fwd = cv2.calcOpticalFlowPyrLK(
                self.prev_img, curr_img, p0, None, **self.lk_params
            )
        except Exception:
            self._update_cache(curr_img, ref_pos, curr_pan_deg, curr_tilt_deg)
            return FlowResult(valid=False, cam_dx=cam_dx, cam_dy=cam_dy)

        if p1 is None or st_fwd is None:
            self._update_cache(curr_img, ref_pos, curr_pan_deg, curr_tilt_deg)
            return FlowResult(valid=False, cam_dx=cam_dx, cam_dy=cam_dy)

        # 4. Backward Lucas-Kanade (curr -> prev) for Consistency Verification
        try:
            p0_back, st_bwd, err_bwd = cv2.calcOpticalFlowPyrLK(
                curr_img, self.prev_img, p1, None, **self.lk_params
            )
        except Exception:
            self._update_cache(curr_img, ref_pos, curr_pan_deg, curr_tilt_deg)
            return FlowResult(valid=False, cam_dx=cam_dx, cam_dy=cam_dy)

        if p0_back is None or st_bwd is None:
            self._update_cache(curr_img, ref_pos, curr_pan_deg, curr_tilt_deg)
            return FlowResult(valid=False, cam_dx=cam_dx, cam_dy=cam_dy)

        # 5. Forward-Backward Consistency Error & Physical Bound Filtering
        p0_flat = p0.reshape(-1, 2)
        p1_flat = p1.reshape(-1, 2)
        p0_back_flat = p0_back.reshape(-1, 2)
        st_fwd_flat = st_fwd.reshape(-1)
        st_bwd_flat = st_bwd.reshape(-1)

        valid_p0: list[np.ndarray] = []
        valid_p1: list[np.ndarray] = []
        fb_errors: list[float] = []

        for i in range(len(p0_flat)):
            if st_fwd_flat[i] == 1 and st_bwd_flat[i] == 1:
                # FB error
                fb_err = float(np.linalg.norm(p0_flat[i] - p0_back_flat[i]))
                # Displacement
                disp_vec = p1_flat[i] - p0_flat[i]
                disp_mag = float(np.linalg.norm(disp_vec))

                if fb_err <= self.cfg.fb_threshold_px and disp_mag <= self.cfg.max_displacement_px:
                    valid_p0.append(p0_flat[i])
                    valid_p1.append(p1_flat[i])
                    fb_errors.append(fb_err)

        if len(valid_p0) < self.cfg.min_valid_features:
            self._update_cache(curr_img, ref_pos, curr_pan_deg, curr_tilt_deg)
            return FlowResult(
                valid=False,
                feature_count=len(valid_p0),
                cam_dx=cam_dx,
                cam_dy=cam_dy,
            )

        # 6. Robust Inlier Clustering & Outlier Rejection (Median-Trimmed)
        disps = np.array(valid_p1) - np.array(valid_p0)  # shape (N, 2)
        dx_arr = disps[:, 0]
        dy_arr = disps[:, 1]

        med_dx = float(np.median(dx_arr))
        med_dy = float(np.median(dy_arr))

        # Deviation from median
        residuals = np.hypot(dx_arr - med_dx, dy_arr - med_dy)
        inlier_mask = residuals <= max(1.5, 2.5 * float(np.median(residuals)))
        inlier_count = int(np.sum(inlier_mask))

        if inlier_count < self.cfg.min_valid_features:
            self._update_cache(curr_img, ref_pos, curr_pan_deg, curr_tilt_deg)
            return FlowResult(
                valid=False,
                feature_count=inlier_count,
                cam_dx=cam_dx,
                cam_dy=cam_dy,
            )

        inlier_dx = dx_arr[inlier_mask]
        inlier_dy = dy_arr[inlier_mask]
        inlier_fb = np.array(fb_errors)[inlier_mask]

        # Aggregated observed viewport displacement
        dx_app = float(np.mean(inlier_dx))
        dy_app = float(np.mean(inlier_dy))

        # 7. Camera Motion Compensation & World/Viewport Velocity Calculation
        # In viewport coordinates:
        vx_vp = float(dx_app / self.dt)
        vy_vp = float(dy_app / self.dt)

        # In world/scene coordinates (camera pan/tilt shift compensated):
        dx_world = float(dx_app + cam_dx)
        dy_world = float(dy_app + cam_dy)
        vx_world = float(dx_world / self.dt)
        vy_world = float(dy_world / self.dt)

        speed = float(np.hypot(vx_vp, vy_vp))

        # 8. Confidence Score Metric
        feature_ratio = min(1.0, inlier_count / 10.0)
        fb_mean = float(np.mean(inlier_fb)) if len(inlier_fb) > 0 else 0.0
        fb_qual = math.exp(-fb_mean / max(0.1, self.cfg.fb_threshold_px))
        disp_std = float(np.hypot(np.std(inlier_dx), np.std(inlier_dy)))
        var_qual = math.exp(-disp_std / 2.0)

        confidence = float(np.clip(feature_ratio * fb_qual * var_qual, 0.05, 1.0))

        # Update cache for next iteration
        self._update_cache(curr_img, (px + dx_app, py + dy_app), curr_pan_deg, curr_tilt_deg)

        return FlowResult(
            valid=True,
            dx_viewport=dx_app,
            dy_viewport=dy_app,
            vx_viewport=vx_vp,
            vy_viewport=vy_vp,
            dx_world=dx_world,
            dy_world=dy_world,
            vx_world=vx_world,
            vy_world=vy_world,
            speed=speed,
            confidence=confidence,
            feature_count=inlier_count,
            fb_error_mean=fb_mean,
            cam_dx=cam_dx,
            cam_dy=cam_dy,
        )

    def _update_cache(
        self, img: np.ndarray, pos: tuple[float, float], pan_deg: float, tilt_deg: float
    ) -> None:
        self.prev_img = img.copy()
        self.prev_pos = pos
        self.prev_pan_deg = pan_deg
        self.prev_tilt_deg = tilt_deg
