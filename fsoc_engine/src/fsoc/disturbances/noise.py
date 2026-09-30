"""
src/fsoc/disturbances/noise.py
================================
Three image noise models applied to viewport frames:
  1. Salt & Pepper  — random white/black pixels (density up to ~10 %)
  2. Gaussian       — additive zero-mean Gaussian noise (sigma up to 20)
  3. Poisson        — shot noise proportional to pixel intensity (gain 0.3–3)

Each model:
  - Takes a uint8 numpy array, returns a uint8 numpy array.
  - Has its own seeded RNG so disturbances are independent and reproducible.
  - Exposes `enabled` flag and `strength` scalar (0.0–1.0) for GUI sliders.
"""
from __future__ import annotations
import cv2
import numpy as np
from dataclasses import dataclass, field


@dataclass
class SaltPepperNoise:
    """
    Randomly sets pixels to 0 (pepper) or 255 (salt).

    Parameters
    ----------
    density : float
        Fraction of pixels affected. PS default ~0.10 (10 %).
        Range [0.0, 0.12].
    enabled : bool
        Master on/off switch.
    seed : int
        RNG seed for reproducibility.
    """
    density: float = 0.10
    enabled: bool = True
    seed: int = 0
    _rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def apply(self, img: np.ndarray) -> np.ndarray:
        """Apply salt & pepper noise and return the result."""
        if not self.enabled or self.density <= 0.0:
            return img
        out = img.copy()
        H, W = out.shape[:2]
        n_pixels = H * W
        n_affected = int(n_pixels * self.density)
        if n_affected <= 0:
            return out
        flat = out.ravel()
        half_n = n_affected // 2
        salt_idx = self._rng.integers(0, n_pixels, half_n)
        pepp_idx = self._rng.integers(0, n_pixels, half_n)
        flat[salt_idx] = 255
        flat[pepp_idx] = 0
        return out


@dataclass
class GaussianNoise:
    """
    Additive zero-mean Gaussian noise.

    Parameters
    ----------
    sigma : float
        Standard deviation of the noise. PS max = 20.
    enabled : bool
    seed : int
    """
    sigma: float = 10.0
    enabled: bool = True
    seed: int = 1
    _rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def apply(self, img: np.ndarray) -> np.ndarray:
        """Add Gaussian noise. Result is clipped to [0, 255] uint8."""
        if not self.enabled or self.sigma <= 0.0:
            return img
        noise = np.empty(img.shape, dtype=np.float32)
        cv2.randn(noise, 0.0, float(self.sigma))
        out = cv2.add(img.astype(np.float32), noise)
        return np.clip(out, 0.0, 255.0, out=out).astype(np.uint8)


@dataclass
class PoissonNoise:
    """
    Shot noise: variance proportional to pixel intensity (photon statistics).
    Implemented as: out = Poisson(img * gain) / gain.

    Parameters
    ----------
    gain : float
        Amplification before Poisson draw. Range [0.3, 3.0].
        Higher gain → more noise at low signal levels.
    enabled : bool
    seed : int
    """
    gain: float = 1.0
    enabled: bool = True
    seed: int = 2
    _rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def apply(self, img: np.ndarray) -> np.ndarray:
        """Apply Poisson (shot) noise and return uint8 result."""
        if not self.enabled or self.gain <= 0.0:
            return img
        scaled = img.astype(np.float32) * float(self.gain)
        noisy = self._rng.poisson(scaled).astype(np.float32)
        noisy /= float(self.gain)
        return np.clip(noisy, 0.0, 255.0, out=noisy).astype(np.uint8)
