"""
src/fsoc/simulation/scene.py
============================
Generates the 2000x2000 full-scene background canvas.
Three background modes:
  flat   - uniform grey (fastest, good for testing)
  perlin - procedural fractal noise (realistic sky/space texture)
  stars  - dark background with scattered faint stars/hot pixels

The canvas is regenerated each call with deterministic seeded RNG.
"""
from __future__ import annotations
import numpy as np
import cv2
from ..core.config import SceneConfig


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def generate_background(cfg: SceneConfig, seed: int | None = None) -> np.ndarray:
    """
    Return a (H, W) uint8 grayscale background canvas.

    Args:
        cfg:  SceneConfig (width, height, background mode, seed).
        seed: Override seed (used by data generator for variety).

    Returns:
        uint8 numpy array of shape (cfg.height, cfg.width).
    """
    rng = np.random.default_rng(seed if seed is not None else cfg.seed)

    if cfg.background == "flat":
        return _flat_background(cfg, rng)
    elif cfg.background == "perlin":
        return _perlin_background(cfg, rng)
    elif cfg.background == "stars":
        return _stars_background(cfg, rng)
    else:
        raise ValueError(f"Unknown background type: '{cfg.background}'")


# ---------------------------------------------------------------------------
# Background generators
# ---------------------------------------------------------------------------

def _flat_background(cfg: SceneConfig, rng: np.random.Generator) -> np.ndarray:
    """Uniform grey with very slight random offset per call."""
    grey_level = int(rng.integers(8, 20))
    canvas = np.full((cfg.height, cfg.width), grey_level, dtype=np.uint8)
    return canvas


def _perlin_background(cfg: SceneConfig, rng: np.random.Generator) -> np.ndarray:
    """
    Approximate Perlin / fractal noise using multi-octave smooth noise.
    Implemented via upscaled random grids (no external library needed).
    """
    H, W = cfg.height, cfg.width
    canvas = np.zeros((H, W), dtype=np.float64)

    # Octaves: scale factor and amplitude weight
    octaves = [
        (16, 0.50),   # very low frequency → large blobs (clouds)
        (8,  0.25),   # medium frequency
        (4,  0.15),   # medium-high
        (2,  0.10),   # high frequency detail
    ]
    total_weight = sum(w for _, w in octaves)

    for scale, weight in octaves:
        small_h = max(2, H // scale)
        small_w = max(2, W // scale)
        noise_small = rng.uniform(0.0, 1.0, (small_h, small_w))
        # Smooth upsample to full resolution
        noise_full = cv2.resize(noise_small, (W, H), interpolation=cv2.INTER_CUBIC)
        canvas += (weight / total_weight) * noise_full

    # Map [0, 1] → dark background range [5, 40]
    canvas = (canvas * 35 + 5).clip(0, 255).astype(np.uint8)

    # Add faint static stars/hot pixels (~0.1% of pixels)
    n_stars = int(H * W * 0.001)
    star_xs = rng.integers(0, W, n_stars)
    star_ys = rng.integers(0, H, n_stars)
    star_vals = rng.integers(40, 100, n_stars).astype(np.uint8)
    canvas[star_ys, star_xs] = np.maximum(canvas[star_ys, star_xs], star_vals)

    return canvas


def _stars_background(cfg: SceneConfig, rng: np.random.Generator) -> np.ndarray:
    """Very dark background with scattered stars of varying brightness."""
    H, W = cfg.height, cfg.width
    canvas = rng.integers(2, 12, (H, W), dtype=np.uint8)

    # Faint stars: ~0.5% pixels
    n_faint = int(H * W * 0.005)
    fx = rng.integers(0, W, n_faint)
    fy = rng.integers(0, H, n_faint)
    canvas[fy, fx] = rng.integers(20, 70, n_faint).astype(np.uint8)

    # Medium stars
    n_med = int(H * W * 0.0005)
    mx = rng.integers(0, W, n_med)
    my = rng.integers(0, H, n_med)
    canvas[my, mx] = rng.integers(70, 140, n_med).astype(np.uint8)

    # Bright distractor blobs (3–5 blobs) that can confuse detector
    n_distractors = int(rng.integers(3, 8))
    for _ in range(n_distractors):
        bx = int(rng.integers(5, W - 5))
        by = int(rng.integers(5, H - 5))
        br = int(rng.integers(3, 12))
        brightness = int(rng.integers(80, 180))
        # Draw a small bright circle
        y_idx, x_idx = np.ogrid[:H, :W]
        mask = (x_idx - bx) ** 2 + (y_idx - by) ** 2 <= br ** 2
        canvas[mask] = np.maximum(canvas[mask], brightness)

    return canvas
