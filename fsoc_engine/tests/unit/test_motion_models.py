"""
tests/unit/test_motion_models.py
=================================
Unit tests for all 7 motion models.
"""
import math
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from fsoc.core.config import default_config, MotionConfig
from fsoc.simulation.motion_models import (
    LineMotion, CircleMotion, Figure8Motion, RandomMotion,
    SpiralMotion, SinusoidalMotion, build_motion_model, _reflect,
)

W, H = 2000, 2000
DT = 1 / 30.0


def make_cfg(model: str) -> MotionConfig:
    cfg = default_config()
    cfg.motion.model = model  # type: ignore[attr-defined]
    return cfg.motion


# -------  _reflect  -------------------------------------------------------

def test_reflect_inside():
    assert _reflect(500, 0, 999) == pytest.approx(500)

def test_reflect_over_hi():
    # 1050 with hi=999: overshoot = 51  -> reflected = 999 - 51 = 948
    assert _reflect(1050, 0, 999) == pytest.approx(948)

def test_reflect_under_lo():
    # -50 with lo=0, hi=999 -> v=-50 -> mod(period=1998) -> 1998-50=1948 > 999 -> 1998-1948=50
    assert _reflect(-50, 0, 999) == pytest.approx(50)


# -------  LineMotion  ------------------------------------------------------

def test_line_motion_starts_at_x0y0():
    cfg = make_cfg("line")
    m = LineMotion(cfg, 100, 200, W, H)
    x, y = m.position(0.0)
    assert x == pytest.approx(100)
    assert y == pytest.approx(200)

def test_line_motion_within_bounds():
    cfg = make_cfg("line")
    m = LineMotion(cfg, 500, 500, W, H)
    for t in range(0, 300):
        x, y = m.position(t * DT)
        assert 0 <= x <= W - 1
        assert 0 <= y <= H - 1


# -------  CircleMotion  ----------------------------------------------------

def test_circle_motion_at_t0_on_right():
    cfg = make_cfg("circle")
    m = CircleMotion(cfg, W, H)
    x, y = m.position(0.0)
    assert x == pytest.approx(W/2 + cfg.circle.radius, abs=1e-3)
    assert y == pytest.approx(H/2, abs=1e-3)

def test_circle_motion_full_period():
    cfg = make_cfg("circle")
    m = CircleMotion(cfg, W, H)
    T = 360.0 / cfg.circle.omega_deg_per_s
    x0, y0 = m.position(0.0)
    xT, yT = m.position(T)
    assert x0 == pytest.approx(xT, abs=1e-3)
    assert y0 == pytest.approx(yT, abs=1e-3)


# -------  Figure8Motion  ---------------------------------------------------

def test_figure8_centre_at_t0():
    cfg = make_cfg("figure8")
    m = Figure8Motion(cfg, W, H)
    x, y = m.position(0.0)
    assert x == pytest.approx(W / 2.0, abs=1e-3)
    assert y == pytest.approx(H / 2.0, abs=1e-3)


# -------  RandomMotion  ----------------------------------------------------

def test_random_motion_within_bounds():
    cfg = make_cfg("random")
    m = RandomMotion(cfg, 1000, 1000, W, H, DT, seed=7)
    for i in range(500):
        x, y = m.position(i * DT)
        assert 0 <= x <= W - 1, f"x={x} out of bounds at step {i}"
        assert 0 <= y <= H - 1, f"y={y} out of bounds at step {i}"

def test_random_motion_deterministic():
    cfg = make_cfg("random")
    m1 = RandomMotion(cfg, 1000, 1000, W, H, DT, seed=42)
    m2 = RandomMotion(cfg, 1000, 1000, W, H, DT, seed=42)
    for i in range(100):
        assert m1.position(i * DT) == m2.position(i * DT)


# -------  SpiralMotion  ----------------------------------------------------

def test_spiral_within_bounds():
    cfg = make_cfg("spiral")
    m = SpiralMotion(cfg, W, H)
    for i in range(600):
        x, y = m.position(i * DT)
        assert 0 <= x <= W - 1
        assert 0 <= y <= H - 1


# -------  SinusoidalMotion  ------------------------------------------------

def test_sinusoidal_within_bounds():
    cfg = make_cfg("sinusoidal")
    m = SinusoidalMotion(cfg, 1000, 1000, W, H)
    for i in range(300):
        x, y = m.position(i * DT)
        assert 0 <= x <= W - 1
        assert 0 <= y <= H - 1


# -------  build_motion_model factory  -------------------------------------

@pytest.mark.parametrize("model", ["line", "circle", "figure8", "random", "spiral", "sinusoidal"])
def test_factory_builds_all_models(model):
    cfg = default_config()
    m = build_motion_model(cfg.motion, 1000, 1000, W, H, DT, seed=0)
    # Override model name directly
    import fsoc.simulation.motion_models as mm
    cfg2 = default_config()
    # Build with explicit model by modifying via dict trick
    raw_cfg = cfg2.motion.model_copy(update={"model": model})
    m2 = build_motion_model(raw_cfg, 1000, 1000, W, H, DT, seed=0)
    x, y = m2.position(1.0)
    assert isinstance(x, float)
    assert isinstance(y, float)
