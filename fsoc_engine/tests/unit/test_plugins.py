"""
Unit tests for NETRA Plugin Playground (Registry, Contracts, Presets, Fallbacks, Swaps).
"""

import pytest
import numpy as np
from fsoc.plugins.registry import registry, PluginRegistry
from fsoc.plugins.contracts import VISION_CONTRACT_DOC, TRACKING_CONTRACT_DOC, CONTROL_CONTRACT_DOC
from fsoc.plugins.defaults import default_vision, default_tracking, default_control
from fsoc.plugins.presets import (
    alpha_beta_tracking,
    single_kalman_tracking,
    ema_tracking,
    pda_tracking,
    p_only_control,
    bang_bang_control,
    lead_lag_control,
    simple_threshold_vision,
    adaptive_threshold_vision,
    psf_fit_vision,
)
from fsoc.core.engine import ClosedLoopEngine
from fsoc.core.config import default_config


def test_registry_initialization():
    reg = PluginRegistry()
    assert reg.get_label("vision") == "NETRA Default"
    assert reg.get_label("tracking") == "NETRA Default"
    assert reg.get_label("control") == "NETRA Default"
    assert not reg.is_custom("vision")
    assert not reg.is_custom("tracking")
    assert not reg.is_custom("control")


def test_pending_swap_application():
    reg = PluginRegistry()
    engine = ClosedLoopEngine()
    reg.register_defaults(engine, default_vision, default_tracking, default_control)

    reg.request("tracking", alpha_beta_tracking, {"alpha": 0.8}, "Custom Alpha Beta")
    assert not reg.is_custom("tracking")  # Not applied yet!

    reg.apply_pending()
    assert reg.is_custom("tracking")
    assert reg.get_label("tracking") == "Custom Alpha Beta"
    assert reg.get_params("tracking") == {"alpha": 0.8}


def test_custom_plugin_crash_fallback():
    reg = PluginRegistry()
    engine = ClosedLoopEngine()
    reg.register_defaults(engine, default_vision, default_tracking, default_control)

    def crashing_tracking(measurement, dt, state, ctx, params):
        raise ValueError("Simulated algorithm crash!")

    reg.request("tracking", crashing_tracking, {}, "Crashing Tracker")
    reg.apply_pending()

    # Call crashing plugin -> Should catch exception, log error, and auto-fallback
    res = reg.call("tracking", {"x": 350.0, "y": 250.0, "confidence": 0.9}, 0.033, {}, {}, {})
    assert isinstance(res, dict)
    assert "x" in res and "y" in res and "vx" in res and "vy" in res
    assert reg.get_status("tracking")["errors"] == 1


def test_alpha_beta_preset():
    state = {}
    meas = {"x": 330.0, "y": 250.0, "confidence": 1.0}
    dt = 0.033

    # Frame 1: Init
    res1 = alpha_beta_tracking(meas, dt, state, {}, {"alpha": 0.85, "beta": 0.005})
    assert res1["x"] == 330.0

    # Frame 2: Predict + Update
    meas2 = {"x": 340.0, "y": 260.0, "confidence": 1.0}
    res2 = alpha_beta_tracking(meas2, dt, state, {}, {"alpha": 0.85, "beta": 0.005})
    assert res2["vx"] > 0
    assert res2["vy"] > 0


def test_p_only_control_preset():
    err = {"ex": 16.0, "ey": -32.0}
    ctx = {"px_per_deg_x": 160.0, "px_per_deg_y": 160.0}
    res = p_only_control(err, {"vx": 0, "vy": 0}, 0.033, {}, ctx, {"kp": 2.0})

    assert pytest.approx(res["pan_rate"]) == 0.2
    assert pytest.approx(res["tilt_rate"]) == -0.4


def test_simple_threshold_vision_preset():
    img = np.zeros((480, 640), dtype=np.uint8)
    img[200, 300] = 220
    res = simple_threshold_vision(img, 640, 480, {}, {"threshold": 180})

    assert res is not None
    assert res["x"] == 300.0
    assert res["y"] == 200.0
    assert res["confidence"] == pytest.approx(220 / 255.0)


def test_engine_run_with_custom_tracking_preset():
    cfg = default_config()
    cfg.pipeline.duration_s = 5.0
    engine = ClosedLoopEngine(cfg=cfg)

    # Swap to Alpha-Beta tracking
    registry.request("tracking", alpha_beta_tracking, {"alpha": 0.85, "beta": 0.005}, "Alpha-Beta Preset")

    # Run closed loop for 100 frames
    for _ in range(100):
        m = engine.step()
        if m is None:
            break

    assert registry.is_custom("tracking")
    assert registry.get_status("tracking")["calls"] >= 15
    assert registry.get_status("tracking")["errors"] == 0
