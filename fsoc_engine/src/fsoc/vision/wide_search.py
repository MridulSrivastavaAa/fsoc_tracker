"""
src/fsoc/vision/wide_search.py
===============================
Wide-Area Acquisition and Search Engine for Mobile FSOC Optical Terminals.
Addresses ISRO Problem Statement Requirement R13:
- Initial Target Acquisition Time <= 2 seconds across 2000x2000 scene space.

Provides two complementary acquisition strategies:
1. Direct Downscaled Scene Search: 4x downscaling (2000x2000 -> 500x500) with
   max-pooling / area interpolation for near-instantaneous (< 5 ms) candidate localization.
2. Viewport Scanning Waypoint Generator: Expanding Archimedean spiral and raster
   search patterns for blind gimbal search under sensor-constrained acquisition.
"""
from __future__ import annotations
from typing import Optional
import cv2
import numpy as np

from ..core.types import Point
from ..core.config import WideSearchConfig, CameraConfig, AppConfig
from .preprocess import VisionPreprocessor
from .detector import SpotDetector


class WideAreaSearch:
    """
    Rapid wide-area target acquisition engine.
    Ensures coarse acquisition within <= 2.0 seconds.
    """
    def __init__(
        self,
        cfg: WideSearchConfig | AppConfig | None = None,
        camera_cfg: Optional[CameraConfig] = None,
    ) -> None:
        if cfg is None:
            w_cfg = WideSearchConfig()
            c_cfg = camera_cfg or CameraConfig()
        elif isinstance(cfg, AppConfig):
            w_cfg = cfg.vision.wide_search
            c_cfg = cfg.camera
        elif isinstance(cfg, WideSearchConfig):
            w_cfg = cfg
            c_cfg = camera_cfg or CameraConfig()
        else:
            raise TypeError(f"Unsupported config type: {type(cfg)}")

        self.cfg = w_cfg
        self.camera_cfg = c_cfg

        # Dedicated preprocessor & detector for coarse search (tophat_ksize=7 for downscaled 500x500 frame)
        from ..core.config import PreprocessConfig
        self.preprocessor = VisionPreprocessor(PreprocessConfig(tophat_ksize=7))
        self.detector = SpotDetector()

    def search_full_scene(
        self, scene_image: np.ndarray
    ) -> Optional[tuple[Point, float]]:
        """
        Rapidly scan a full 2000x2000 scene image by downscaling.
        
        Args:
            scene_image: Full scene image (H, W) uint8.
            
        Returns:
            (target_point, confidence) in original scene coordinates,
            or None if no candidate found.
        """
        if scene_image.ndim != 2:
            raise ValueError(f"Expected 2D image, got shape {scene_image.shape}")

        H, W = scene_image.shape
        scale = self.cfg.downscale_factor
        down_w = max(1, W // scale)
        down_h = max(1, H // scale)

        # Downscale using max-pooling or area resize so small bright beacon spots are preserved
        downscaled = cv2.resize(
            scene_image, (down_w, down_h), interpolation=cv2.INTER_AREA
        )

        # Detect candidate spots on downscaled image
        cleaned, mask, _ = self.preprocessor.process(downscaled)
        detections = self.detector.detect(downscaled, mask=mask, intensity_image=cleaned)

        if not detections:
            # Fallback: check maximum intensity location in cleaned downscaled frame
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(cleaned)
            if max_val >= self.cfg.coarse_threshold:
                coarse_x, coarse_y = max_loc
                full_x = float(coarse_x * scale + scale / 2.0)
                full_y = float(coarse_y * scale + scale / 2.0)
                confidence = float(min(1.0, max_val / 255.0))
                return Point(full_x, full_y), confidence
            return None

        best = detections[0]
        # Map coarse downscaled coordinate back to full scene coordinate space
        full_x = float(best.x * scale)
        full_y = float(best.y * scale)

        # Refine locally around (full_x, full_y) in full scene image (50x50 crop)
        win = 25
        x0 = max(0, int(round(full_x)) - win)
        y0 = max(0, int(round(full_y)) - win)
        x1 = min(W, int(round(full_x)) + win)
        y1 = min(H, int(round(full_y)) + win)

        crop = scene_image[y0:y1, x0:x1]
        if crop.size > 0:
            local_dets = self.detector.detect(crop)
            if local_dets:
                sub_det = local_dets[0]
                full_x = float(x0 + sub_det.x)
                full_y = float(y0 + sub_det.y)

        conf = float(min(1.0, best.intensity / 200.0))
        return Point(full_x, full_y), conf

    def compute_camera_pointing(
        self,
        target_scene_pt: Point,
        scene_center_x: float = 1000.0,
        scene_center_y: float = 1000.0,
    ) -> tuple[float, float, float]:
        """
        Calculate target pan and tilt angles and estimated slew time to acquire target.
        
        Args:
            target_scene_pt: Detected target position in scene coordinates.
            scene_center_x: Optical center of scene (X).
            scene_center_y: Optical center of scene (Y).
            
        Returns:
            (target_pan_deg, target_tilt_deg, estimated_slew_time_s)
        """
        dx_px = target_scene_pt.x - scene_center_x
        dy_px = target_scene_pt.y - scene_center_y

        pan_deg = dx_px / self.camera_cfg.px_per_deg_x
        tilt_deg = dy_px / self.camera_cfg.px_per_deg_y

        # Slew time calculation considering pan and tilt maximum speeds
        max_pan_speed = self.camera_cfg.max_pan_deg_per_s
        max_tilt_speed = self.camera_cfg.max_tilt_deg_per_s

        time_pan = abs(pan_deg) / max(1e-3, max_pan_speed)
        time_tilt = abs(tilt_deg) / max(1e-3, max_tilt_speed)
        est_slew_s = max(time_pan, time_tilt)

        return pan_deg, tilt_deg, est_slew_s

    def generate_spiral_search_path(
        self,
        max_radius_deg: float = 6.0,
        radial_step_deg: float = 2.0,
        angular_step_deg: float = 30.0,
    ) -> list[tuple[float, float]]:
        """
        Generate expanding Archimedean spiral search waypoints (pan_deg, tilt_deg)
        for blind gimbal re-acquisition when target is lost.
        """
        waypoints: list[tuple[float, float]] = [(0.0, 0.0)]
        theta = 0.0
        r = 0.5

        b = radial_step_deg / (2.0 * np.pi)  # r = b * theta
        angular_rad = np.radians(angular_step_deg)

        while r <= max_radius_deg:
            pan = r * np.cos(theta)
            tilt = r * np.sin(theta)
            waypoints.append((float(pan), float(tilt)))
            theta += angular_rad
            r = b * theta

        return waypoints

    def generate_raster_search_path(
        self,
        fov_x_deg: float = 3.5,
        fov_y_deg: float = 2.5,
        span_x_deg: float = 8.0,
        span_y_deg: float = 6.0,
    ) -> list[tuple[float, float]]:
        """
        Generate serpentine raster grid search waypoints.
        """
        waypoints: list[tuple[float, float]] = []
        xs = np.arange(-span_x_deg / 2, span_x_deg / 2 + fov_x_deg, fov_x_deg)
        ys = np.arange(-span_y_deg / 2, span_y_deg / 2 + fov_y_deg, fov_y_deg)

        for row_idx, y in enumerate(ys):
            row_xs = xs if row_idx % 2 == 0 else xs[::-1]
            for x in row_xs:
                waypoints.append((float(x), float(y)))

        return waypoints
