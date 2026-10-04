"""
Unit tests for A/B Comparison Engine (ab_runner.py).
"""

import pytest
from fsoc.plugins.ab_runner import run_ab_comparison
from fsoc.plugins.presets import alpha_beta_tracking, p_only_control


def test_ab_runner_same_seed_default():
    # If custom_func is None, both default and custom are NETRA default -> RMSE delta should be ~0%
    res = run_ab_comparison(slot="tracking", custom_func=None, max_frames=50)
    assert pytest.approx(res["default"]["rmse"], abs=1e-2) == res["custom"]["rmse"]
    assert pytest.approx(res["delta"]["rmse_delta_pct"], abs=1.0) == 0.0


def test_ab_runner_alpha_beta_vs_imm():
    res = run_ab_comparison(
        slot="tracking",
        custom_func=alpha_beta_tracking,
        custom_params={"alpha": 0.85, "beta": 0.005},
        custom_label="Alpha-Beta Filter",
        max_frames=100,
    )
    assert "default" in res
    assert "custom" in res
    assert "verdict" in res
    assert res["custom"]["n_frames"] >= 50


def test_ab_runner_p_only_control():
    res = run_ab_comparison(
        slot="control",
        custom_func=p_only_control,
        custom_params={"kp": 1.5},
        custom_label="P-Only Controller",
        max_frames=100,
    )
    assert "delta" in res
    assert res["slot"] == "control"
