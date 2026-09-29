"""
src/fsoc/disturbances/platform_motion.py
=========================================
Slow, low-frequency drift of the entire platform (satellite/UAV body motion).
Unlike jitter (fast, random, per-frame), platform motion is smooth and
correlated across frames — it represents the vehicle's overall movement.

PS spec: ±20 px/frame, Linear mandatory; circular/random/spiral/fig-8 optional.

Implementation: maintains a running (dx, dy) offset that is applied as an
affine shift to the full-frame image before the camera crops its viewport.
The drift evolves smoothly using a low-frequency oscillator or random walk.
"""
from __future__ import annotations
import math
import numpy as np
import cv2
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PlatformMotion:
    """
    Simulates slow platform body drift applied to the full scene image.

    Parameters
    ----------
    mode : str
        'linear'    — constant velocity drift (mandatory)
        'circular'  — circular oscillation
        'random'    — smooth random walk (low-frequency)
        'spiral'    — inward/outward spiral drift
        'figure8'   — Lissajous figure-of-eight
    max_px : float
        Maximum single-frame shift magnitude (PS: ±20 px/frame).
    enabled : bool
    seed : int
    """
    mode: Literal["linear", "circular", "random", "spiral", "figure8"] = "linear"
    max_px: float = 10.0           # default: moderate drift
    enabled: bool = True
    seed: int = 20
    fps: float = 30.0

    # Internal state
    _t: float = field(default=0.0, init=False, repr=False)
    _vx: float = field(default=0.0, init=False, repr=False)
    _vy: float = field(default=0.0, init=False, repr=False)
    _ox: float = field(default=0.0, init=False, repr=False)  # current offset x
    _oy: float = field(default=0.0, init=False, repr=False)  # current offset y
    _rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)
        dt = 1.0 / self.fps
        # Linear mode: pick a constant slow velocity
        speed = self.max_px * 0.3   # 30 % of max gives smooth drift
        angle = self._rng.uniform(0, 2 * math.pi)
        self._vx = speed * math.cos(angle)
        self._vy = speed * math.sin(angle)

    def step(self, dt: float) -> tuple[float, float]:
        """
        Advance the platform motion by one time step.
        Returns the (dx, dy) shift to apply to the full scene image.
        """
        if not self.enabled or self.max_px <= 0.0:
            return 0.0, 0.0

        self._t += dt

        if self.mode == "linear":
            dx = self._vx * dt
            dy = self._vy * dt

        elif self.mode == "circular":
            omega = 2 * math.pi * 0.1  # 0.1 Hz oscillation
            R = self.max_px * 0.5
            prev_x = R * math.cos(omega * (self._t - dt))
            prev_y = R * math.sin(omega * (self._t - dt))
            curr_x = R * math.cos(omega * self._t)
            curr_y = R * math.sin(omega * self._t)
            dx = curr_x - prev_x
            dy = curr_y - prev_y

        elif self.mode == "random":
            # Smooth random walk: accelerate gently, clip to max_px per frame
            ax = self._rng.uniform(-2.0, 2.0)
            ay = self._rng.uniform(-2.0, 2.0)
            self._vx = float(np.clip(self._vx + ax * dt, -self.max_px, self.max_px))
            self._vy = float(np.clip(self._vy + ay * dt, -self.max_px, self.max_px))
            dx = self._vx * dt
            dy = self._vy * dt

        elif self.mode == "spiral":
            omega = 2 * math.pi * 0.05
            r0, k = 2.0, 0.5
            r_prev = r0 + k * (self._t - dt)
            r_curr = r0 + k * self._t
            prev_x = r_prev * math.cos(omega * (self._t - dt))
            prev_y = r_prev * math.sin(omega * (self._t - dt))
            curr_x = r_curr * math.cos(omega * self._t)
            curr_y = r_curr * math.sin(omega * self._t)
            dx = float(np.clip(curr_x - prev_x, -self.max_px, self.max_px))
            dy = float(np.clip(curr_y - prev_y, -self.max_px, self.max_px))

        elif self.mode == "figure8":
            omega = 2 * math.pi * 0.05
            Ax, Ay = self.max_px * 3, self.max_px * 1.5
            prev_x = Ax * math.sin(omega * (self._t - dt))
            prev_y = Ay * math.sin(2 * omega * (self._t - dt))
            curr_x = Ax * math.sin(omega * self._t)
            curr_y = Ay * math.sin(2 * omega * self._t)
            dx = float(np.clip(curr_x - prev_x, -self.max_px, self.max_px))
            dy = float(np.clip(curr_y - prev_y, -self.max_px, self.max_px))

        else:
            dx, dy = 0.0, 0.0

        # Clip single-frame shift to PS max
        dx = float(np.clip(dx, -self.max_px, self.max_px))
        dy = float(np.clip(dy, -self.max_px, self.max_px))

        self._ox += dx
        self._oy += dy
        return dx, dy

    def apply(self, img: np.ndarray, dt: float) -> np.ndarray:
        """
        Compute the next drift step and apply it as an affine shift to img.
        Returns shifted uint8 image (same shape as input).
        """
        dx, dy = self.step(dt)
        if dx == 0.0 and dy == 0.0:
            return img
        M = np.array([[1.0, 0.0, dx],
                      [0.0, 1.0, dy]], dtype=np.float32)
        H, W = img.shape[:2]
        return cv2.warpAffine(img, M, (W, H),
                              flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)

    def reset(self) -> None:
        """Reset state to t=0 (used when SimulatedSource resets)."""
        self._t = 0.0
        self._ox = 0.0
        self._oy = 0.0

    def enable_mode(self, mode: str, max_shift: float = 5.0) -> None:
        """Helper to set platform motion mode and max shift."""
        self.mode = mode  # type: ignore[assignment]
        self.max_px = max_shift
        self.enabled = True
