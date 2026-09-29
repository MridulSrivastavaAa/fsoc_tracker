"""
src/fsoc/advanced/turbulence_estimator.py
=========================================
Real-Time Atmospheric Turbulence & Scintillation Estimator (ATAC-PSM).
Calculates:
- Scintillation Index sigma_I^2 = Var(I) / Mean(I)^2
- Atmospheric Turbulence Regime: WEAK (<0.2), MODERATE (0.2 - 1.0), STRONG (>1.0)
- Empirical Fried Parameter r0 estimate (cm)
- Scintillation Deep Fade Detector
"""
from __future__ import annotations
from typing import Optional
from enum import Enum
import numpy as np

from ..core.config import AdvancedConfig, AppConfig


class TurbulenceRegime(str, Enum):
    WEAK = "WEAK"          # sigma_I^2 < 0.2
    MODERATE = "MODERATE"  # 0.2 <= sigma_I^2 <= 1.0
    STRONG = "STRONG"      # sigma_I^2 > 1.0 (Saturation regime)


class ScintillationEstimator:
    """
    Sliding-window estimator for optical scintillation index and atmospheric turbulence.
    """
    def __init__(self, cfg: AdvancedConfig | AppConfig | None = None) -> None:
        if cfg is None:
            a_cfg = AdvancedConfig()
        elif isinstance(cfg, AppConfig):
            a_cfg = cfg.advanced
        elif isinstance(cfg, AdvancedConfig):
            a_cfg = cfg
        else:
            raise TypeError(f"Unsupported config type: {type(cfg)}")

        self.cfg = a_cfg
        self.window_size = self.cfg.scintillation_window_frames
        self.intensity_buffer: list[float] = []

        # Current estimated metrics
        self.scintillation_index: float = 0.0
        self.mean_intensity: float = 0.0
        self.fried_parameter_cm: float = 15.0  # default 15 cm (good astronomical seeing)
        self.regime: TurbulenceRegime = TurbulenceRegime.WEAK
        self.is_deep_fade: bool = False

    def update(self, intensity: Optional[float]) -> dict:
        """
        Record instantaneous peak intensity and update turbulence estimates.
        
        Args:
            intensity: Detected beacon peak intensity (0 - 255), or None if obscured.
            
        Returns:
            Dictionary with current turbulence diagnostic metrics.
        """
        if intensity is not None and intensity > 0.0:
            self.intensity_buffer.append(float(intensity))
            if len(self.intensity_buffer) > self.window_size:
                self.intensity_buffer.pop(0)

        # Compute statistics if sufficient samples available
        if len(self.intensity_buffer) >= 5:
            arr = np.array(self.intensity_buffer, dtype=np.float64)
            mean_i = float(np.mean(arr))
            var_i = float(np.var(arr))
            self.mean_intensity = mean_i

            if mean_i > 1e-3:
                self.scintillation_index = float(np.clip(var_i / (mean_i ** 2), 0.0, 5.0))
            else:
                self.scintillation_index = 0.0

            # Classify regime
            if self.scintillation_index < 0.2:
                self.regime = TurbulenceRegime.WEAK
            elif self.scintillation_index <= 1.0:
                self.regime = TurbulenceRegime.MODERATE
            else:
                self.regime = TurbulenceRegime.STRONG

            # Estimate Fried parameter r0 (cm)
            # Higher scintillation -> smaller r0 (stronger optical phase distortion)
            # r0 roughly scales inversely with sigma_I
            self.fried_parameter_cm = float(np.clip(18.0 / (1.0 + 3.0 * self.scintillation_index), 2.0, 25.0))

            # Deep fade detection: current sample drops below threshold ratio of mean
            if intensity is not None:
                self.is_deep_fade = bool(intensity < self.mean_intensity * self.cfg.fade_threshold_ratio)
            else:
                self.is_deep_fade = True
        else:
            self.scintillation_index = 0.0
            self.regime = TurbulenceRegime.WEAK
            self.is_deep_fade = False

        return {
            "scintillation_index": self.scintillation_index,
            "regime": self.regime.value,
            "fried_parameter_cm": self.fried_parameter_cm,
            "mean_intensity": self.mean_intensity,
            "is_deep_fade": self.is_deep_fade,
        }

    def reset(self) -> None:
        """Reset estimator buffers."""
        self.intensity_buffer.clear()
        self.scintillation_index = 0.0
        self.mean_intensity = 0.0
        self.fried_parameter_cm = 15.0
        self.regime = TurbulenceRegime.WEAK
        self.is_deep_fade = False
