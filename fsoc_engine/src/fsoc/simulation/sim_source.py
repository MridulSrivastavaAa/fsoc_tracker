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
import hashlib
import math
import tempfile
from pathlib import Path
from typing import Optional
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
        #: Waypoints (scene px) for the 'user' trajectory; serialised to CSV on rebuild.
        self.waypoints_px: list[tuple[float, float]] = []
        self.wp_speed_px_s: float = 96.0
        self._motion: MotionModel = self._build_motion(cfg, x0, y0, seed=_seed + 1)

        self._frame_index: int = 0
        self._t: float = 0.0
        #: Local time handed to the motion model. Kept separate from _t so a mid-run
        #: trajectory rebuild can restart the pattern phase at 0 (no teleport).
        self._mt: float = 0.0
        self._dt = cfg.pipeline.dt
        self._max_frames: int = int(cfg.pipeline.duration_s * cfg.pipeline.fps)
        self.visible: bool = True
        self.occlusion_intervals: list[tuple[float, float]] = []

        # --- Optional channel/truth effects (driven by the web bridge) ---
        #: per-frame probability the beacon is physically hidden (sensor dropout)
        self.dropout_prob: float = 0.0
        #: Gaussian jitter added to the true beacon position, px
        self.target_noise_px: float = 0.0
        #: render a dimmer, differently sized decoy spot (sun glint / other object)
        self.decoy: bool = False
        self.decoy_target: Optional[Target] = None
        # Extra RNGs for the effects above (kept across resets for reproducibility).
        self._fx_rng = np.random.default_rng(_seed + 2)
        self._reset_rng = np.random.default_rng(_seed + 7)
        self._fixed_start = cfg.target.initial_x is not None and cfg.target.initial_y is not None
        # Per-frame truth status, read by the telemetry bridge.
        self.last_beacon: tuple[float, float] = (x0, y0)
        self.last_visible: bool = True
        self.last_occluded: bool = False
        self.last_dropped: bool = False
        self.last_decoy: Optional[tuple[float, float]] = None

    def set_occlusion_schedule(self, period_s: float, dur_s: float) -> None:
        """Fill occlusion_intervals with a deterministic periodic cloud-outage schedule."""
        self.occlusion_intervals = []
        if period_s > 0 and dur_s > 0:
            horizon = max(self._t + self._max_frames * self._dt, 3600.0)
            t0 = 0.0
            while t0 < horizon:
                self.occlusion_intervals.append((t0, t0 + dur_s))
                t0 += period_s

    def reseed_start(self) -> None:
        """Draw a fresh random beacon start (used on explicit run reset, PS item 6)."""
        if self._fixed_start:
            return
        margin = self._cfg.target.size_px * 2
        rng = self._reset_rng
        self._x0 = float(rng.integers(margin, self._cfg.scene.width - margin))
        self._y0 = float(rng.integers(margin, self._cfg.scene.height - margin))

    # ------------------------------------------------------------------
    # Motion model construction (initial build, reset, and mid-run rebuild)
    # ------------------------------------------------------------------

    def _build_motion(self, cfg: AppConfig, x0: float, y0: float, seed: int) -> MotionModel:
        """Build the configured motion model anchored at (x0, y0).

        Pattern models (circle / figure-8 / spiral) are positioned so that
        position(local t = 0) == (x0, y0): the beacon never teleports when the
        trajectory or its parameters change mid-run.
        """
        W = float(cfg.scene.width)
        H = float(cfg.scene.height)
        m = cfg.motion
        margin = float(cfg.target.size_px) * 3 + 32.0
        cx, cy = x0, y0

        def _clip(v: float, lo: float, hi: float) -> float:
            return v if lo > hi else min(max(v, lo), hi)

        if m.model == "circle":
            R = float(m.circle.radius)
            # Centre one radius away from the beacon, on the side towards scene centre.
            dx0, dy0 = x0 - W / 2.0, y0 - H / 2.0
            n = math.hypot(dx0, dy0)
            ux, uy = (dx0 / n, dy0 / n) if n > 1e-6 else (1.0, 0.0)
            cx = _clip(x0 - R * ux, R + margin, W - R - margin)
            cy = _clip(y0 - R * uy, R + margin, H - R - margin)
            if R + margin > W - R - margin:
                cx = W / 2.0
            if R + margin > H - R - margin:
                cy = H / 2.0
            # Phase so that position(0) lands exactly on (x0, y0).
            px, py = x0 - cx, y0 - cy
            m.circle.phase_offset_deg = math.degrees(math.atan2(py, px)) if (abs(px) > 1e-9 or abs(py) > 1e-9) else 0.0
        elif m.model == "figure8":
            Ax = float(m.figure8.amplitude_x)
            Ay = float(m.figure8.amplitude_y)
            cx = _clip(x0, Ax + margin, W - Ax - margin)
            cy = _clip(y0, Ay + margin, H - Ay - margin)
        elif m.model == "spiral":
            Rmax = min(W, H) * 0.45
            lo_x, hi_x = Rmax + 4.0, W - Rmax - 4.0
            lo_y, hi_y = Rmax + 4.0, H - Rmax - 4.0
            cx = _clip(x0 - float(m.spiral.r0), lo_x, hi_x)
            cy = _clip(y0, lo_y, hi_y)
        elif m.model == "sinusoidal":
            Ay = float(m.sinusoidal.amplitude_y)
            cx = _clip(x0, margin, W - margin)
            cy = _clip(y0, Ay + margin, H - Ay - margin)
        elif m.model == "user" and self.waypoints_px:
            m.user.csv_path = self._write_waypoints_csv(cfg, x0, y0)

        return build_motion_model(m, cx, cy, cfg.scene.width, cfg.scene.height, cfg.pipeline.dt, seed=seed)

    def _write_waypoints_csv(self, cfg: AppConfig, x0: float, y0: float) -> str:
        """Serialise the waypoint tour (scene px) as a [t, x, y] CSV for UserDefinedMotion."""
        wps = [(float(x), float(y)) for x, y in self.waypoints_px]
        if not wps:
            wps = [(x0, y0)]
        speed = max(1.0, float(self.wp_speed_px_s))
        pts = [(x0, y0)] + wps + [wps[0]]
        dt = 0.1
        rows: list[tuple[float, float, float]] = []
        t = 0.0
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            seg = math.hypot(bx - ax, by - ay)
            dur = max(dt, seg / speed)
            steps = max(1, int(dur / dt))
            for k in range(steps):
                f = k / steps
                rows.append((t + dur * f, ax + (bx - ax) * f, ay + (by - ay) * f))
            t += dur
        rows.append((t, pts[-1][0], pts[-1][1]))
        key = hashlib.md5(repr((wps, round(speed, 3), round(x0, 2), round(y0, 2))).encode()).hexdigest()[:10]
        path = Path(tempfile.gettempdir()) / f"fsoc_waypoints_{key}.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write("t,x,y\n")
            for r in rows:
                f.write(f"{r[0]:.4f},{r[1]:.2f},{r[2]:.2f}\n")
        return str(path)

    def rebuild_motion(self) -> None:
        """Rebuild the trajectory from the *current* beacon position (mid-run config
        changes: trajectory kind, speed, amplitude, period, heading, waypoints)."""
        bx, by = self.last_beacon
        self._motion = self._build_motion(self._cfg, bx, by, seed=self._bg_seed + 1)
        self._mt = 0.0

    # ------------------------------------------------------------------
    # FrameSource interface
    # ------------------------------------------------------------------

    def next_frame(self) -> FullFrame | None:
        """Return the next simulation frame, or None when duration is exhausted."""
        if self._frame_index >= self._max_frames:
            return None

        # Query motion model for beacon world position
        bx, by = self._motion.position(self._mt)

        # Target motion noise (physical pointing wander of the beacon)
        if self.target_noise_px > 0.0:
            bx += float(self._fx_rng.normal(0.0, self.target_noise_px))
            by += float(self._fx_rng.normal(0.0, self.target_noise_px))
            bx = float(np.clip(bx, 0.0, self._cfg.scene.width - 1.0))
            by = float(np.clip(by, 0.0, self._cfg.scene.height - 1.0))
        self.last_beacon = (bx, by)

        # Copy background so frame instances are independent
        canvas = self._background.copy()

        # Check occlusion intervals (scheduled cloud outage) and random dropouts
        is_occluded = any(t_start <= self._t <= t_end for t_start, t_end in self.occlusion_intervals)
        is_dropped = self.dropout_prob > 0.0 and float(self._fx_rng.random()) < self.dropout_prob
        is_visible = self.visible and not is_occluded and not is_dropped
        self.last_occluded = is_occluded
        self.last_dropped = is_dropped
        self.last_visible = is_visible

        # Render beacon onto canvas if visible
        if is_visible:
            self._target.render_onto(canvas, bx, by)

        # Optional decoy spot: a dimmer, differently sized object that drifts
        # around the field (models sun glint / another spacecraft).
        gt_pts: list[Point] = []
        if is_visible:
            gt_pts.append(Point(bx, by))
            # The decoy is only added behind the beacon so ground_truth[0] stays
            # the true target (occlusion/dropout hides both, like a cloud would).
            if self.decoy and self.decoy_target is not None:
                du = 1.1 * math.sin(self._t * 0.37) + 0.6   # deg
                dv = 0.9 * math.cos(self._t * 0.29) - 0.4   # deg
                dx = bx + du * 160.0
                dy = by - dv * 160.0
                if 0 <= dx < self._cfg.scene.width and 0 <= dy < self._cfg.scene.height:
                    self.decoy_target.render_onto(canvas, dx, dy)
                    gt_pts.append(Point(dx, dy))
                    self.last_decoy = (dx, dy)
                else:
                    self.last_decoy = None
            else:
                self.last_decoy = None
        else:
            self.last_decoy = None

        frame = FullFrame(
            image=canvas,
            frame_index=self._frame_index,
            timestamp_s=self._t,
            ground_truth=gt_pts,
        )

        self._frame_index += 1
        self._t += self._dt
        self._mt += self._dt
        return frame

    def reset(self, reseed: bool = False) -> None:
        """Rewind to frame 0, regenerate background with same seed, rebuild motion model.
        If reseed is True, a new random beacon start is drawn (unless fixed).
        """
        if reseed:
            self.reseed_start()
        self._frame_index = 0
        self._t = 0.0
        self._mt = 0.0
        self.last_visible = True
        self.last_occluded = False
        self.last_dropped = False
        self.last_decoy = None
        self._background = generate_background(self._cfg.scene, seed=self._bg_seed)
        self._motion = self._build_motion(self._cfg, self._x0, self._y0, seed=self._bg_seed + 1)

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
