"""
src/fsoc/simulation/sim_source.py
==================================
SimulatedSource: concrete FrameSource backed by the virtual scene.

Each call to next_frame():
  1. Advances simulation time by dt = 1/fps.
  2. Queries motion model for beacon position at time t.
  3. Renders the background (fresh copy so beacon doesn't accumulate).
  4. Renders the beacon onto the canvas.
  5. Returns a FullFrame with exact ground-truth.
"""
from __future__ import annotations
import numpy as np
from ..core.frame_source import FrameSource
from ..core.types import FullFrame, Point
from ..core.config import AppConfig
from .scene import generate_background
from .targets import Target
from .motion_models import build_motion_model, MotionModel


class SimulatedSource(FrameSource):
    """
    Infinite simulation frame source.
    Produces deterministic, labelled frames at cfg.pipeline.fps.
    """

    def __init__(self, cfg: AppConfig, seed: int | None = None) -> None:
        self._cfg = cfg
        _seed = seed if seed is not None else cfg.pipeline.seed

        # Determine initial beacon position
        rng = np.random.default_rng(_seed)
        margin = cfg.target.size_px * 2
        x0 = float(cfg.target.initial_x) if cfg.target.initial_x is not None \
            else float(rng.integers(margin, cfg.scene.width - margin))
        y0 = float(cfg.target.initial_y) if cfg.target.initial_y is not None \
            else float(rng.integers(margin, cfg.scene.height - margin))

        self._x0 = x0
        self._y0 = y0

        # Pre-generate static background (regenerated on reset)
        self._bg_seed = _seed
        self._background = generate_background(cfg.scene, seed=self._bg_seed)

        # Target renderer
        self._target = Target(cfg.target)

        # Motion model
        self._motion: MotionModel = build_motion_model(
            cfg.motion, x0, y0,
            cfg.scene.width, cfg.scene.height,
            cfg.pipeline.dt,
            seed=_seed + 1,
        )

        self._frame_index: int = 0
        self._t: float = 0.0
        self._dt = cfg.pipeline.dt
        self._max_frames: int = int(cfg.pipeline.duration_s * cfg.pipeline.fps)
        self.visible: bool = True
        self.occlusion_intervals: list[tuple[float, float]] = []

    # ------------------------------------------------------------------
    # FrameSource interface
    # ------------------------------------------------------------------

    def next_frame(self) -> FullFrame | None:
        """Return the next simulation frame, or None when duration is exhausted."""
        if self._frame_index >= self._max_frames:
            return None

        # Query motion model for beacon world position
        bx, by = self._motion.position(self._t)

        # Copy background so frame instances are independent
        canvas = self._background.copy()

        # Check occlusion intervals
        is_occluded = any(t_start <= self._t <= t_end for t_start, t_end in self.occlusion_intervals)
        is_visible = self.visible and not is_occluded

        # Render beacon onto canvas if visible
        if is_visible:
            self._target.render_onto(canvas, bx, by)

        frame = FullFrame(
            image=canvas,
            frame_index=self._frame_index,
            timestamp_s=self._t,
            ground_truth=[Point(bx, by)] if is_visible else [],
        )

        self._frame_index += 1
        self._t += self._dt
        return frame

    def reset(self) -> None:
        """Rewind to frame 0, regenerate background with same seed, rebuild motion model."""
        self._frame_index = 0
        self._t = 0.0
        self._background = generate_background(self._cfg.scene, seed=self._bg_seed)
        self._motion = build_motion_model(
            self._cfg.motion,
            self._x0,
            self._y0,
            self._cfg.scene.width,
            self._cfg.scene.height,
            self._dt,
            seed=self._bg_seed + 1,
        )

    @property
    def fps(self) -> float:
        return self._cfg.pipeline.fps

    @property
    def has_ground_truth(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def frame_index(self) -> int:
        return self._frame_index

    @property
    def current_time(self) -> float:
        return self._t
