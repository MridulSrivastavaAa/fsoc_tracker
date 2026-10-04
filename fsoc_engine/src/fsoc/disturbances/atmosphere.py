"""
src/fsoc/disturbances/atmosphere.py
=====================================
Atmospheric degradation models applied to the viewport frame.

Five named conditions (from PS spec) + turbulence:
  clear     — no effect (identity, I'= I)
  haze      — reduced contrast + slight brightness increase
  fog       — heavy contrast reduction + blur + brightness boost
  rain      — diagonal streak overlay + slight contrast reduction
  low_light — strong brightness reduction + increased shot noise

Turbulence sub-effects (independent, stackable):
  beam wander     — slow random offset of the entire image
  scintillation   — multiplicative log-normal intensity flicker
  blur            — varying Gaussian blur (simulates refractive turbulence)

All effects are parametric (strength 0.0–1.0) and seeded for reproducibility.

Formulas (atmosphere):
  I' = alpha * I + beta      (linear contrast/brightness)
  alpha: [0, 1] — contrast reduction
  beta:  any    — brightness offset
"""
from __future__ import annotations
import math
import numpy as np
import cv2
from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Named atmospheric conditions
# ---------------------------------------------------------------------------

# Condition params: (alpha, beta, blur_sigma)
_CONDITIONS: dict[str, tuple[float, float, float]] = {
    "clear":     (1.00,   0,  0.0),
    "haze":      (0.70,  15,  0.5),
    "fog":       (0.45,  35,  1.5),
    "rain":      (0.80,   0,  0.0),
    "low_light": (0.40, -10,  0.0),
}


@dataclass
class AtmosphereEffect:
    """
    Applies a named atmospheric condition to the viewport image.

    Parameters
    ----------
    condition : str
        One of 'clear', 'haze', 'fog', 'rain', 'low_light'.
    strength : float
        Blending factor [0.0 = identity, 1.0 = full effect].
    enabled : bool
    seed : int
    """
    condition: Literal["clear", "haze", "fog", "rain", "low_light"] = "clear"
    strength: float = 1.0       # 0 = no effect, 1 = full
    enabled: bool = True
    seed: int = 30
    _rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def apply(self, img: np.ndarray) -> np.ndarray:
        if not self.enabled or self.condition == "clear" or self.strength <= 0.0:
            return img

        alpha_full, beta_full, blur_sigma = _CONDITIONS[self.condition]

        # Interpolate towards the full effect based on strength
        alpha = 1.0 + (alpha_full - 1.0) * self.strength
        beta  = beta_full * self.strength

        # Linear contrast/brightness
        out = img.astype(np.float32) * alpha + beta

        # Fog: Gaussian blur to simulate scattering
        if self.condition == "fog" and blur_sigma > 0.0:
            blur_s = blur_sigma * self.strength
            ks = max(3, int(6 * blur_s + 1) | 1)
            out = cv2.GaussianBlur(out, (ks, ks), blur_s)

        # Rain: random diagonal streaks
        if self.condition == "rain":
            out = self._add_rain_streaks(out)

        return np.clip(out, 0, 255).astype(np.uint8)

    def _add_rain_streaks(self, img: np.ndarray) -> np.ndarray:
        """Overlay random diagonal rain streaks on a float32 image."""
        H, W = img.shape[:2]
        n_streaks = int(self._rng.integers(40, 120) * self.strength)
        streak_len = int(self._rng.integers(8, 25))
        out = img.copy()
        for _ in range(n_streaks):
            x = int(self._rng.integers(0, W))
            y = int(self._rng.integers(0, H))
            brightness = float(self._rng.uniform(180, 255))
            # Diagonal streak: slope ~80° from vertical
            for k in range(streak_len):
                sx = x + k // 5
                sy = y + k
                if 0 <= sx < W and 0 <= sy < H:
                    out[sy, sx] = brightness
        return out

    def set_condition(self, condition: str, strength: float = 1.0) -> None:
        """Helper method to update condition and strength."""
        self.condition = condition  # type: ignore[assignment]
        self.strength = strength
        self.enabled = (condition != "clear")


# ---------------------------------------------------------------------------
# Turbulence sub-effects
# ---------------------------------------------------------------------------

@dataclass
class TurbulenceEffect:
    """
    Optical turbulence: beam wander, scintillation, and refractive blur.

    Parameters
    ----------
    wander_max_px : float
        Maximum beam wander offset [px]. Range 0–10.
    scintillation_sigma : float
        Std-dev of log-normal intensity flicker. Range 0–0.5.
    blur_sigma : float
        Gaussian blur sigma for refractive index fluctuations. Range 0–2.
    enabled : bool
    seed : int
    """
    wander_max_px: float = 3.0
    scintillation_sigma: float = 0.15
    blur_sigma: float = 0.5
    enabled: bool = False       # off by default; user activates
    seed: int = 40
    _rng: np.random.Generator = field(init=False, repr=False)
    _wander_x: float = field(default=0.0, init=False, repr=False)
    _wander_y: float = field(default=0.0, init=False, repr=False)
    #: Most recent frame's wander offset (px) and scintillation factor — telemetry HUD.
    last_wander: tuple[float, float] = (0.0, 0.0)
    last_scint: float = 1.0

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def apply(self, img: np.ndarray) -> np.ndarray:
        if not self.enabled:
            self.last_wander = (0.0, 0.0)
            self.last_scint = 1.0
            return img

        out = img.astype(np.float32)

        # 1. Scintillation: multiplicative log-normal flicker
        if self.scintillation_sigma > 0.0:
            flicker = float(self._rng.lognormal(0.0, self.scintillation_sigma))
            flicker = float(np.clip(flicker, 0.5, 2.0))
            out = out * flicker
            self.last_scint = flicker
        else:
            self.last_scint = 1.0

        # 2. Refractive blur (varying kernel per frame)
        if self.blur_sigma > 0.0:
            sigma = float(abs(self._rng.normal(self.blur_sigma, self.blur_sigma * 0.3)))
            sigma = max(0.1, sigma)
            ks = max(3, int(6 * sigma + 1) | 1)
            out = cv2.GaussianBlur(out, (ks, ks), sigma)

        # 3. Beam wander: slow random walk offset
        if self.wander_max_px > 0.0:
            self._wander_x += float(self._rng.normal(0.0, 0.5))
            self._wander_y += float(self._rng.normal(0.0, 0.5))
            self._wander_x = float(np.clip(self._wander_x,
                                           -self.wander_max_px, self.wander_max_px))
            self._wander_y = float(np.clip(self._wander_y,
                                           -self.wander_max_px, self.wander_max_px))
            self.last_wander = (self._wander_x, self._wander_y)
            M = np.array([[1.0, 0.0, self._wander_x],
                          [0.0, 1.0, self._wander_y]], dtype=np.float32)
            H, W = out.shape[:2]
            out = cv2.warpAffine(out.astype(np.uint8), M, (W, H),
                                 flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE).astype(np.float32)

        return np.clip(out, 0, 255).astype(np.uint8)
