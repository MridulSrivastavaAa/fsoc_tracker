"""
src/fsoc/vision/flow_gating.py
==============================
Adaptive Optical Flow Confidence Gating and Reliability Estimation (Step 3).

Estimates a continuous reliability weight w_flow in [0, 1] for auxiliary
optical flow velocity measurements based on:
1. Feature count & forward-backward consistency error
2. Spatial flow variance & raw tracking confidence
3. Velocity innovation disagreement against IMM dynamic prediction
4. High-frequency camera jitter & spatial oscillation detection
"""
from __future__ import annotations
import math
from collections import deque
from typing import Optional, Tuple
import numpy as np

from ..core.types import FlowResult
from ..core.config import AdaptiveFlowConfig


class AdaptiveFlowGater:
    """
    Deterministic reliability and confidence estimator for optical flow velocity cues.
    Produces a continuous fusion weight flow_weight in [0, 1] and gating telemetry.
    """
    def __init__(self, cfg: Optional[AdaptiveFlowConfig] = None, dt: float = 1.0 / 30.0) -> None:
        self.cfg = cfg or AdaptiveFlowConfig()
        self.dt = float(dt)

        # Sliding window history of observed viewport displacements for jitter detection
        self._disp_history: deque[tuple[float, float]] = deque(maxlen=self.cfg.jitter_history_len)
        self.reset()

    def reset(self) -> None:
        """Clear displacement history and internal state."""
        self._disp_history.clear()

    def update_history(self, dx: float, dy: float) -> None:
        """Add observed displacement to sliding window."""
        self._disp_history.append((float(dx), float(dy)))

    def compute_jitter_score(self) -> tuple[float, float]:
        """
        Compute high-frequency jitter score and jitter quality factor q_jitter in [0, 1].

        Returns:
            (jitter_score_px, q_jitter)
        """
        if len(self._disp_history) < 3:
            return 0.0, 1.0

        disps = np.array(self._disp_history, dtype=np.float64)  # shape (K, 2)
        diffs = disps[1:] - disps[:-1]  # acceleration / jerk steps

        # RMS acceleration magnitude
        step_mags = np.hypot(diffs[:, 0], diffs[:, 1])
        rms_accel = float(np.sqrt(np.mean(np.square(step_mags))))

        # Directional reversal count (dot product of consecutive displacements < 0)
        dots = disps[:-1, 0] * disps[1:, 0] + disps[:-1, 1] * disps[1:, 1]
        reversals = np.sum(dots < 0)
        reversal_ratio = float(reversals / max(1, len(dots)))

        # Jitter score combines high acceleration with rapid oscillatory sign reversals
        jitter_score = float(rms_accel * (0.5 + 0.75 * reversal_ratio))

        # Smooth suppression factor: q_jitter -> 0 when jitter_score >> threshold
        thresh = max(1.0, self.cfg.jitter_threshold_px)
        norm_j = jitter_score / thresh
        q_jitter = float(1.0 / (1.0 + (norm_j ** 2) * self.cfg.jitter_suppression_factor))
        q_jitter = float(np.clip(q_jitter, 0.0, 1.0))

        return jitter_score, q_jitter

    def evaluate_flow(
        self,
        flow: Optional[FlowResult],
        pred_vx: float = 0.0,
        pred_vy: float = 0.0,
        pred_var_vx: float = 100.0,
        pred_var_vy: float = 100.0,
    ) -> FlowResult:
        """
        Evaluate optical flow reliability and compute adaptive weight flow_weight in [0, 1].

        Args:
            flow: Raw FlowResult from OpticalFlowTracker.
            pred_vx: IMM predicted viewport velocity X (px/s).
            pred_vy: IMM predicted viewport velocity Y (px/s).
            pred_var_vx: Predicted velocity variance X (px/s)^2.
            pred_var_vy: Predicted velocity variance Y (px/s)^2.

        Returns:
            Updated FlowResult with weight, quality, innovation, jitter_score, and gate_reason.
        """
        if flow is None or not flow.valid:
            # When flow is unavailable or invalid
            return FlowResult(
                valid=False,
                weight=0.0,
                quality=0.0,
                innovation=0.0,
                jitter_score=0.0,
                gate_reason="NO_FLOW" if flow is None else "INVALID_FLOW",
            )

        if not self.cfg.enabled:
            # If adaptive gating is disabled, pass flow with full nominal confidence
            return FlowResult(
                valid=True,
                dx_viewport=flow.dx_viewport,
                dy_viewport=flow.dy_viewport,
                vx_viewport=flow.vx_viewport,
                vy_viewport=flow.vy_viewport,
                dx_world=flow.dx_world,
                dy_world=flow.dy_world,
                vx_world=flow.vx_world,
                vy_world=flow.vy_world,
                speed=flow.speed,
                confidence=flow.confidence,
                feature_count=flow.feature_count,
                fb_error_mean=flow.fb_error_mean,
                cam_dx=flow.cam_dx,
                cam_dy=flow.cam_dy,
                weight=float(flow.confidence),
                quality=float(flow.confidence),
                innovation=0.0,
                jitter_score=0.0,
                gate_reason="GOOD_FLOW",
            )

        # Update sliding window displacement history
        self.update_history(flow.dx_viewport, flow.dy_viewport)

        # 1. Feature Count Quality Factor q_feat in [0, 1]
        n_full = max(3, self.cfg.min_features_full_weight)
        q_feat = min(1.0, flow.feature_count / float(n_full))

        # 2. Forward-Backward Consistency Quality Factor q_fb in [0, 1]
        tau_fb = max(0.1, self.cfg.fb_error_scale_px)
        q_fb = math.exp(-flow.fb_error_mean / tau_fb)

        # 3. Raw Flow Quality Metric q_flow in [0, 1]
        q_flow = float(np.clip(q_feat * q_fb * flow.confidence, 0.0, 1.0))

        # 4. Velocity Disagreement / Normalized Innovation NIS
        # Innovation residual y = z_flow - v_pred
        y_vx = flow.vx_viewport - pred_vx
        y_vy = flow.vy_viewport - pred_vy

        # Base measurement variance at 30 fps
        sigma_v2_base = 2.0 * 4.0 / (self.dt ** 2)  # ~7200 (px/s)^2
        s_vx = pred_var_vx + sigma_v2_base
        s_vy = pred_var_vy + sigma_v2_base

        nis_vel = float((y_vx ** 2) / max(1.0, s_vx) + (y_vy ** 2) / max(1.0, s_vy))
        nis_scale = max(0.5, self.cfg.nis_scale)
        q_innov = math.exp(-nis_vel / nis_scale)
        q_innov = float(np.clip(q_innov, 0.0, 1.0))

        # 5. Jitter Detection & Suppression Factor q_jitter in [0, 1]
        jitter_score, q_jitter = self.compute_jitter_score()

        # 6. Composite Fusion Weight w_flow in [0, 1]
        w_flow = float(q_flow * q_innov * q_jitter)

        # Min threshold cutoff
        if w_flow < self.cfg.min_weight_threshold or flow.feature_count < 2:
            w_flow = 0.0

        w_flow = float(np.clip(w_flow, 0.0, 1.0))

        # 7. Diagnostic Gating Reason Classification
        if flow.feature_count < 3:
            gate_reason = "LOW_FEATURE_COUNT"
        elif flow.fb_error_mean > 1.2:
            gate_reason = "HIGH_FB_ERROR"
        elif jitter_score > self.cfg.jitter_threshold_px and q_jitter < 0.45:
            gate_reason = "HIGH_JITTER"
        elif nis_vel > self.cfg.nis_gate and q_innov < 0.45:
            gate_reason = "HIGH_INNOVATION"
        elif w_flow >= self.cfg.min_weight_threshold:
            gate_reason = "GOOD_FLOW"
        else:
            gate_reason = "INVALID_FLOW"

        return FlowResult(
            valid=bool(w_flow > 0.0),
            dx_viewport=flow.dx_viewport,
            dy_viewport=flow.dy_viewport,
            vx_viewport=flow.vx_viewport,
            vy_viewport=flow.vy_viewport,
            dx_world=flow.dx_world,
            dy_world=flow.dy_world,
            vx_world=flow.vx_world,
            vy_world=flow.vy_world,
            speed=flow.speed,
            confidence=flow.confidence,
            feature_count=flow.feature_count,
            fb_error_mean=flow.fb_error_mean,
            cam_dx=flow.cam_dx,
            cam_dy=flow.cam_dy,
            weight=w_flow,
            quality=q_flow,
            innovation=nis_vel,
            jitter_score=jitter_score,
            gate_reason=gate_reason,
        )
