"""
src/fsoc/disturbances/jitter.py
================================
Camera platform vibration: per-frame random sub-pixel translation of the
viewport image, simulating mechanical vibrations of the gimbal/platform.

PS spec: ±20 px/frame maximum.
Implementation: sub-pixel affine shift via cv2.warpAffine with
INTER_LINEAR interpolation so fractional pixel offsets are smooth.

The shift is drawn fresh every call (stateless per-frame) from a seeded RNG.
"""
from __future__ import annotations
import numpy as np
import cv2
from dataclasses import dataclass, field


@dataclass
class CameraJitter:
    """
    Per-frame camera jitter (vibration) applied as a 2-D translation.

    Parameters
    ----------
    max_px : float
        Maximum jitter amplitude in pixels. PS default 20 px.
    distribution : str
        'uniform'  — flat distribution in [-max_px, +max_px]
        'gaussian' — Gaussian with sigma = max_px / 3 (3-sigma ≈ max_px)
    enabled : bool
    seed : int
    """
    max_px: float = 20.0
    distribution: str = "gaussian"   # 'uniform' | 'gaussian'
    enabled: bool = True
    seed: int = 10
    _rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def apply(self, img: np.ndarray) -> np.ndarray:
        """
        Apply a random 2-D translation to img and return the result.
        Border areas are filled with 0 (black) where the shift exposes edges.
        """
        if not self.enabled or self.max_px <= 0.0:
            return img

        # Sample shift
        if self.distribution == "gaussian":
            sigma = self.max_px / 3.0
            dx = float(np.clip(self._rng.normal(0.0, sigma), -self.max_px, self.max_px))
            dy = float(np.clip(self._rng.normal(0.0, sigma), -self.max_px, self.max_px))
        else:  # uniform
            dx = float(self._rng.uniform(-self.max_px, self.max_px))
            dy = float(self._rng.uniform(-self.max_px, self.max_px))

        # Build affine translation matrix  [ 1 0 dx ]
        #                                  [ 0 1 dy ]
        M = np.array([[1.0, 0.0, dx],
                      [0.0, 1.0, dy]], dtype=np.float32)

        H, W = img.shape[:2]
        out = cv2.warpAffine(img, M, (W, H),
                             flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=0)
        return out

    def sample_shift(self) -> tuple[float, float]:
        """Return (dx, dy) without applying — used by platform_motion tests."""
        if self.distribution == "gaussian":
            sigma = self.max_px / 3.0
            dx = float(np.clip(self._rng.normal(0.0, sigma), -self.max_px, self.max_px))
            dy = float(np.clip(self._rng.normal(0.0, sigma), -self.max_px, self.max_px))
        else:
            dx = float(self._rng.uniform(-self.max_px, self.max_px))
            dy = float(self._rng.uniform(-self.max_px, self.max_px))
        return dx, dy
