"""
src/fsoc/simulation/targets.py
===============================
Renders an optical beacon spot onto the scene canvas at a given (x, y) position.
Supports square, circle, and cross shapes with optional Gaussian PSF blur.
"""
from __future__ import annotations
import numpy as np
import cv2
from ..core.config import TargetConfig


class Target:
    """
    Renders one optical beacon onto a provided canvas in-place.
    All rendering is done directly on NumPy arrays (no OpenCV drawing state).
    """

    def __init__(self, cfg: TargetConfig) -> None:
        self.shape = cfg.shape
        self.size_px = cfg.size_px
        self.brightness = cfg.brightness
        self.psf_sigma = cfg.psf_sigma

        # Build the base patch (un-blurred, un-blended) once
        self._patch = self._build_patch()

    def _build_patch(self) -> np.ndarray:
        """Create a float64 patch of shape (size_px, size_px)."""
        s = self.size_px
        patch = np.zeros((s, s), dtype=np.float64)
        half = s // 2
        cx, cy = s / 2.0 - 0.5, s / 2.0 - 0.5  # sub-pixel centre

        if self.shape == "square":
            patch[:, :] = float(self.brightness)

        elif self.shape == "circle":
            ys, xs = np.ogrid[:s, :s]
            dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
            patch[dist <= half] = float(self.brightness)

        elif self.shape == "cross":
            patch[half, :] = float(self.brightness)       # horizontal bar
            patch[:, half] = float(self.brightness)       # vertical bar

        # Apply Gaussian PSF blur to simulate optical diffraction
        if self.psf_sigma > 0.0:
            # kernel size: odd number >= 3
            ks = max(3, int(6 * self.psf_sigma + 1) | 1)
            patch = cv2.GaussianBlur(patch, (ks, ks), self.psf_sigma)

        return patch.astype(np.float64)

    def render_onto(self, canvas: np.ndarray, x: float, y: float) -> tuple[int, int]:
        """
        Additively blend the beacon patch onto the canvas at sub-pixel position (x, y).
        Returns the integer top-left corner (for bounding box information).

        Args:
            canvas: Full-scene uint8 grayscale image, modified in place.
            x, y:   Sub-pixel beacon centre in canvas coordinates.

        Returns:
            (top_left_x, top_left_y) of the patch.
        """
        H, W = canvas.shape
        s = self.size_px

        # Integer top-left corner
        x0 = int(round(x)) - s // 2
        y0 = int(round(y)) - s // 2

        # Clip patch against canvas boundaries
        px_start = max(0, -x0)
        py_start = max(0, -y0)
        px_end = min(s, W - x0)
        py_end = min(s, H - y0)

        cx_start = max(0, x0)
        cy_start = max(0, y0)
        cx_end = cx_start + (px_end - px_start)
        cy_end = cy_start + (py_end - py_start)

        if px_end <= px_start or py_end <= py_start:
            return x0, y0  # completely off-screen

        # Additive blend, clamp to uint8 range
        region = canvas[cy_start:cy_end, cx_start:cx_end].astype(np.float64)
        region += self._patch[py_start:py_end, px_start:px_end]
        canvas[cy_start:cy_end, cx_start:cx_end] = np.clip(region, 0, 255).astype(np.uint8)

        return x0, y0
