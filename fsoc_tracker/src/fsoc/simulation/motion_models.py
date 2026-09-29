"""
src/fsoc/simulation/motion_models.py
=====================================
All 7 target motion models. Each model is a pure function of time (deterministic)
so scenarios are exactly reproducible.

Coordinate system: x → right, y → down (screen pixels).
Boundaries: the target reflects off the scene edges so it never leaves the canvas.
"""
from __future__ import annotations
import math
import numpy as np
from ..core.config import MotionConfig


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class MotionModel:
    """Abstract base – subclasses override position(t)."""

    def __init__(self, scene_w: int, scene_h: int) -> None:
        self.scene_w = scene_w
        self.scene_h = scene_h

    def position(self, t: float) -> tuple[float, float]:
        """Return (x, y) at time t seconds."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Straight line with border reflection
# ---------------------------------------------------------------------------

class LineMotion(MotionModel):
    """Linear motion with perfect reflections at scene boundaries."""

    def __init__(self, cfg: MotionConfig, x0: float, y0: float,
                 scene_w: int, scene_h: int) -> None:
        super().__init__(scene_w, scene_h)
        self.x0, self.y0 = x0, y0
        self.vx = cfg.line.vx
        self.vy = cfg.line.vy

    def position(self, t: float) -> tuple[float, float]:
        x = _reflect(self.x0 + self.vx * t, 0, self.scene_w - 1)
        y = _reflect(self.y0 + self.vy * t, 0, self.scene_h - 1)
        return x, y


# ---------------------------------------------------------------------------
# Circular
# ---------------------------------------------------------------------------

class CircleMotion(MotionModel):
    """Uniform circular motion around a configurable centre (default = scene centre)."""

    def __init__(
        self,
        cfg: MotionConfig,
        scene_w_or_x0: float | int,
        scene_h_or_y0: float | int,
        scene_w: Optional[int] = None,
        scene_h: Optional[int] = None,
    ) -> None:
        if scene_w is None or scene_h is None:
            w, h = int(scene_w_or_x0), int(scene_h_or_y0)
            super().__init__(w, h)
            self.cx = w / 2.0
            self.cy = h / 2.0
        else:
            super().__init__(scene_w, scene_h)
            self.cx = float(scene_w_or_x0)
            self.cy = float(scene_h_or_y0)

        self.R = cfg.circle.radius
        self.omega = math.radians(cfg.circle.omega_deg_per_s)  # rad/s
        # Phase offset in radians (0 = start right, -pi/2 = start top)
        self.phase = math.radians(cfg.circle.phase_offset_deg)

    def position(self, t: float) -> tuple[float, float]:
        angle = self.omega * t + self.phase
        x = self.cx + self.R * math.cos(angle)
        y = self.cy + self.R * math.sin(angle)
        return float(x), float(y)


# ---------------------------------------------------------------------------
# Figure-of-8 (Lissajous)
# ---------------------------------------------------------------------------

class Figure8Motion(MotionModel):
    """Lissajous figure-of-8: x=A sin(wt), y=B sin(2wt)."""

    def __init__(self, cfg: MotionConfig, scene_w: int, scene_h: int) -> None:
        super().__init__(scene_w, scene_h)
        self.cx = scene_w / 2.0
        self.cy = scene_h / 2.0
        self.Ax = cfg.figure8.amplitude_x
        self.Ay = cfg.figure8.amplitude_y
        self.omega = math.radians(cfg.figure8.omega_deg_per_s)

    def position(self, t: float) -> tuple[float, float]:
        x = self.cx + self.Ax * math.sin(self.omega * t)
        y = self.cy + self.Ay * math.sin(2.0 * self.omega * t)
        return float(x), float(y)


# ---------------------------------------------------------------------------
# Bounded random walk
# ---------------------------------------------------------------------------

class RandomMotion(MotionModel):
    """
    Bounded random-walk on velocity. Velocity is updated at each dt step.
    The model is seeded from the config seed so it is deterministic.
    """

    def __init__(self, cfg: MotionConfig, x0: float, y0: float,
                 scene_w: int, scene_h: int,
                 dt: float, seed: int = 0) -> None:
        super().__init__(scene_w, scene_h)
        self.max_accel = cfg.random.max_accel
        self.dt = dt
        self._rng = np.random.default_rng(seed)
        # Pre-generate full trajectory up to a large T (enough for 10 min @30 Hz)
        self._steps = 20_000
        self._xs, self._ys = self._generate(x0, y0)

    def _generate(self, x0: float, y0: float) -> tuple[np.ndarray, np.ndarray]:
        xs = np.empty(self._steps)
        ys = np.empty(self._steps)
        x, y, vx, vy = x0, y0, 0.0, 0.0
        max_speed = 200.0  # px/s
        for i in range(self._steps):
            ax = self._rng.uniform(-self.max_accel, self.max_accel)
            ay = self._rng.uniform(-self.max_accel, self.max_accel)
            vx = float(np.clip(vx + ax * self.dt, -max_speed, max_speed))
            vy = float(np.clip(vy + ay * self.dt, -max_speed, max_speed))
            x = _reflect(x + vx * self.dt, 0, self.scene_w - 1)
            y = _reflect(y + vy * self.dt, 0, self.scene_h - 1)
            xs[i] = x
            ys[i] = y
        return xs, ys

    def position(self, t: float) -> tuple[float, float]:
        idx = int(t / self.dt) % self._steps
        return float(self._xs[idx]), float(self._ys[idx])


# ---------------------------------------------------------------------------
# Spiral (optional)
# ---------------------------------------------------------------------------

class SpiralMotion(MotionModel):
    """Outward spiral from scene centre, wraps when radius exceeds limit."""

    def __init__(self, cfg: MotionConfig, scene_w: int, scene_h: int) -> None:
        super().__init__(scene_w, scene_h)
        self.cx = scene_w / 2.0
        self.cy = scene_h / 2.0
        self.r0 = cfg.spiral.r0
        self.k = cfg.spiral.k
        self.omega = math.radians(cfg.spiral.omega_deg_per_s)
        self._max_r = min(scene_w, scene_h) * 0.45

    def position(self, t: float) -> tuple[float, float]:
        # Wrap radius so it bounces back inward when it hits max
        r_raw = self.r0 + self.k * t
        period = 2 * self._max_r
        r_mod = r_raw % period
        r = r_mod if r_mod <= self._max_r else period - r_mod
        x = self.cx + r * math.cos(self.omega * t)
        y = self.cy + r * math.sin(self.omega * t)
        return float(x), float(y)


# ---------------------------------------------------------------------------
# Sinusoidal (optional)
# ---------------------------------------------------------------------------

class SinusoidalMotion(MotionModel):
    """Horizontal constant velocity + vertical sinusoidal oscillation."""

    def __init__(self, cfg: MotionConfig, x0: float, y0: float,
                 scene_w: int, scene_h: int) -> None:
        super().__init__(scene_w, scene_h)
        self.x0, self.y0 = x0, y0
        self.vx = cfg.sinusoidal.vx
        self.Ay = cfg.sinusoidal.amplitude_y
        self.omega = math.radians(cfg.sinusoidal.omega_deg_per_s)

    def position(self, t: float) -> tuple[float, float]:
        x = _reflect(self.x0 + self.vx * t, 0, self.scene_w - 1)
        y = _reflect(self.y0 + self.Ay * math.sin(self.omega * t), 0, self.scene_h - 1)
        return float(x), float(y)


# ---------------------------------------------------------------------------
# User-defined from CSV (optional)
# ---------------------------------------------------------------------------

class UserDefinedMotion(MotionModel):
    """
    Reads a CSV with columns [t, x, y] and interpolates.
    Wraps around at the end of the file.
    """

    def __init__(self, cfg: MotionConfig, scene_w: int, scene_h: int) -> None:
        super().__init__(scene_w, scene_h)
        import csv, pathlib
        path = pathlib.Path(cfg.user.csv_path)
        if not path.exists():
            raise FileNotFoundError(f"User trajectory CSV not found: {path}")
        ts, xs, ys = [], [], []
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts.append(float(row["t"]))
                xs.append(float(row["x"]))
                ys.append(float(row["y"]))
        self._ts = np.array(ts)
        self._xs = np.array(xs)
        self._ys = np.array(ys)
        self._duration = float(self._ts[-1] - self._ts[0])

    def position(self, t: float) -> tuple[float, float]:
        t_wrapped = (t % self._duration) + self._ts[0]
        x = float(np.interp(t_wrapped, self._ts, self._xs))
        y = float(np.interp(t_wrapped, self._ts, self._ys))
        return x, y


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_motion_model(cfg: MotionConfig,
                       x0: float, y0: float,
                       scene_w: int, scene_h: int,
                       dt: float,
                       seed: int = 0) -> MotionModel:
    """Return the appropriate MotionModel based on config.motion.model."""
    name = cfg.model
    if name == "line":
        return LineMotion(cfg, x0, y0, scene_w, scene_h)
    elif name == "circle":
        return CircleMotion(cfg, x0, y0, scene_w, scene_h)
    elif name == "figure8":
        return Figure8Motion(cfg, scene_w, scene_h)
    elif name == "random":
        return RandomMotion(cfg, x0, y0, scene_w, scene_h, dt, seed=seed)
    elif name == "spiral":
        return SpiralMotion(cfg, scene_w, scene_h)
    elif name == "sinusoidal":
        return SinusoidalMotion(cfg, x0, y0, scene_w, scene_h)
    elif name == "user":
        return UserDefinedMotion(cfg, scene_w, scene_h)
    else:
        raise ValueError(f"Unknown motion model: '{name}'")


# ---------------------------------------------------------------------------
# Utility: boundary reflection
# ---------------------------------------------------------------------------

def _reflect(value: float, lo: float, hi: float) -> float:
    """Reflect a value between lo and hi (like a ball bouncing off walls)."""
    span = hi - lo
    if span <= 0:
        return lo
    # Shift so lo=0, reflect, shift back
    v = value - lo
    period = 2 * span
    v_mod = v % period
    if v_mod <= span:
        return lo + v_mod
    else:
        return lo + period - v_mod
