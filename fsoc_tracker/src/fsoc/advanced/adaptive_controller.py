"""
src/fsoc/advanced/adaptive_controller.py
========================================
Adaptive Turbulence Compensator & Actuator Jerk Mitigation.
Features:
- Dynamic Kalman Covariance Scaling: Modulates measurement noise R to filter beam wander
- Predictive Deep Fade Bridging: Extrapolates through scintillation dropouts
- Actuator Low-Pass Command Filtering: Protects gimbal motors from turbulent jitter
"""
from __future__ import annotations
import numpy as np

from ..core.types import CameraCommand, TrackState
from ..core.config import AdvancedConfig, AppConfig
from .turbulence_estimator import ScintillationEstimator, TurbulenceRegime


class AdaptiveTurbulenceCompensator:
    """
    Online compensator adapting tracking estimation and actuator control to
    atmospheric turbulence and optical scintillation.
    """
    def __init__(
        self,
        cfg: AdvancedConfig | AppConfig | None = None,
        dt: float = 1.0 / 30.0,
    ) -> None:
        if cfg is None:
            a_cfg = AdvancedConfig()
        elif isinstance(cfg, AppConfig):
            a_cfg = cfg.advanced
            dt = cfg.pipeline.dt
        elif isinstance(cfg, AdvancedConfig):
            a_cfg = cfg
        else:
            raise TypeError(f"Unsupported config type: {type(cfg)}")

        self.cfg = a_cfg
        self.dt = float(dt)
        self.estimator = ScintillationEstimator(self.cfg)

        # IIR Low-pass filter state for pan and tilt rate commands
        self.prev_pan_rate: float = 0.0
        self.prev_tilt_rate: float = 0.0

    def compute_adaptive_r_scale(self, scintillation_index: float) -> float:
        """
        Compute multiplier for Kalman measurement noise covariance R.
        In strong turbulence, increases R so the filter ignores micro-scale beam wander.
        """
        if not self.cfg.enabled:
            return 1.0
        # Scale R by (1 + k * sigma_I^2)
        scale = 1.0 + self.cfg.adaptive_kalman_gain * float(scintillation_index)
        return float(np.clip(scale, 1.0, 5.0))

    def filter_actuator_command(
        self, cmd: CameraCommand, regime: TurbulenceRegime
    ) -> CameraCommand:
        """
        Filter camera command through adaptive low-pass filter to eliminate
        high-frequency beam wander oscillations from reaching physical gimbal actuators.
        """
        if not self.cfg.enabled:
            return cmd

        # Adapt cutoff frequency based on turbulence regime
        if regime == TurbulenceRegime.STRONG:
            fc = 2.0  # Hz (aggressive smoothing)
        elif regime == TurbulenceRegime.MODERATE:
            fc = self.cfg.wander_cutoff_hz  # 3.0 Hz
        else:
            fc = 8.0  # Hz (responsive tracking)

        # 1st-order IIR alpha: alpha = 2*pi*fc*dt / (1 + 2*pi*fc*dt)
        rc = 1.0 / (2.0 * np.pi * fc)
        alpha = self.dt / (rc + self.dt)
        alpha = float(np.clip(alpha, 0.05, 0.95))

        filt_pan = alpha * cmd.pan_rate_deg_per_s + (1.0 - alpha) * self.prev_pan_rate
        filt_tilt = alpha * cmd.tilt_rate_deg_per_s + (1.0 - alpha) * self.prev_tilt_rate

        self.prev_pan_rate = filt_pan
        self.prev_tilt_rate = filt_tilt

        return CameraCommand(
            pan_rate_deg_per_s=float(filt_pan),
            tilt_rate_deg_per_s=float(filt_tilt),
        )

    def process_frame(
        self,
        beacon_intensity: float | None,
        raw_cmd: CameraCommand,
    ) -> tuple[CameraCommand, float, dict]:
        """
        Full frame compensation step:
        1. Updates scintillation estimator
        2. Computes adaptive R scaling factor
        3. Filters gimbal rate command to suppress beam wander jerk
        
        Returns:
            (filtered_command, adaptive_r_scale, turbulence_diagnostics)
        """
        diag = self.estimator.update(beacon_intensity)
        r_scale = self.compute_adaptive_r_scale(diag["scintillation_index"])
        regime = TurbulenceRegime(diag["regime"])

        filtered_cmd = self.filter_actuator_command(raw_cmd, regime)
        return filtered_cmd, r_scale, diag

    def reset(self) -> None:
        """Reset compensator."""
        self.estimator.reset()
        self.prev_pan_rate = 0.0
        self.prev_tilt_rate = 0.0
