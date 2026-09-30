"""
tests/unit/test_flow_gating.py
==============================
Unit & Regression Tests for Adaptive Optical Flow Confidence Gating (Step 3).

Test Coverage:
1. Reliable flow -> high weight (>= 0.70), reason GOOD_FLOW
2. Low feature count -> reduced weight / gate LOW_FEATURE_COUNT
3. High forward-backward error -> exponential deweighting / HIGH_FB_ERROR
4. Strong IMM-flow velocity disagreement (high NIS) -> deweighting / HIGH_INNOVATION
5. High camera jitter -> deweighting / HIGH_JITTER
6. Clean Figure-8 -> flow remains useful and trusted
7. Fast target -> flow remains useful and trusted
8. Invalid flow -> weight = 0.0, reason INVALID_FLOW
9. Weight 0 -> exact fallback behavior (matches pure position IMM)
10. Weight bounded in [0, 1] across extreme inputs
11. Deterministic behavior with fixed inputs
"""
import math
import numpy as np
import pytest

from fsoc.core.config import default_config, AdaptiveFlowConfig
from fsoc.core.types import FlowResult, TrackState
from fsoc.vision.flow_gating import AdaptiveFlowGater
from fsoc.tracking.imm import IMMTracker


class TestAdaptiveFlowGating:
    def test_reliable_flow_high_weight(self) -> None:
        """Reliable flow with many inliers, low error, low NIS, and low jitter receives high weight."""
        gater = AdaptiveFlowGater(dt=1.0 / 30.0)

        # Feed a sequence of steady 2 px/frame displacements (smooth flight)
        for _ in range(5):
            gater.update_history(2.0, 1.0)

        raw_flow = FlowResult(
            valid=True,
            dx_viewport=2.0,
            dy_viewport=1.0,
            vx_viewport=60.0,
            vy_viewport=30.0,
            speed=67.08,
            confidence=0.90,
            feature_count=12,
            fb_error_mean=0.15,
        )

        res = gater.evaluate_flow(
            raw_flow,
            pred_vx=58.0,
            pred_vy=31.0,
            pred_var_vx=50.0,
            pred_var_vy=50.0,
        )

        assert res.valid
        assert res.weight >= 0.70
        assert res.quality >= 0.70
        assert res.gate_reason == "GOOD_FLOW"
        assert res.jitter_score < 2.0

    def test_low_feature_count_reduced_weight(self) -> None:
        """Low feature count (1-2 points) significantly reduces weight and flags LOW_FEATURE_COUNT."""
        gater = AdaptiveFlowGater()
        raw_flow = FlowResult(
            valid=True,
            dx_viewport=2.0,
            dy_viewport=1.0,
            vx_viewport=60.0,
            vy_viewport=30.0,
            confidence=0.80,
            feature_count=2,
            fb_error_mean=0.20,
        )

        res = gater.evaluate_flow(raw_flow, pred_vx=60.0, pred_vy=30.0)
        assert res.weight <= 0.25
        assert res.gate_reason == "LOW_FEATURE_COUNT"

    def test_high_fb_error_reduced_weight(self) -> None:
        """High forward-backward consistency error (> 2 px) heavily deweights flow."""
        gater = AdaptiveFlowGater()
        raw_flow = FlowResult(
            valid=True,
            dx_viewport=3.0,
            dy_viewport=2.0,
            vx_viewport=90.0,
            vy_viewport=60.0,
            confidence=0.80,
            feature_count=10,
            fb_error_mean=2.8,  # very high FB error
        )

        res = gater.evaluate_flow(raw_flow, pred_vx=90.0, pred_vy=60.0)
        assert res.weight < 0.20
        assert res.gate_reason == "HIGH_FB_ERROR"

    def test_strong_imm_flow_disagreement_reduced_weight(self) -> None:
        """When flow velocity strongly contradicts IMM prediction (high NIS), weight is deweighted."""
        gater = AdaptiveFlowGater(dt=1.0 / 30.0)
        raw_flow = FlowResult(
            valid=True,
            dx_viewport=10.0,
            dy_viewport=0.0,
            vx_viewport=300.0,
            vy_viewport=0.0,
            confidence=0.85,
            feature_count=10,
            fb_error_mean=0.20,
        )

        # IMM predicts opposite velocity (-50 px/s)
        res = gater.evaluate_flow(
            raw_flow,
            pred_vx=-50.0,
            pred_vy=0.0,
            pred_var_vx=200.0,
            pred_var_vy=200.0,
        )

        assert res.innovation > 9.0  # High NIS
        assert res.weight < 0.20
        assert res.gate_reason == "HIGH_INNOVATION"

    def test_high_jitter_reduced_weight(self) -> None:
        """High-frequency oscillating displacements (+20, -20) trigger jitter deweighting."""
        gater = AdaptiveFlowGater(dt=1.0 / 30.0)

        # Feed oscillating displacements simulating +/-20 px camera jitter
        for _ in range(3):
            gater.update_history(20.0, 0.0)
            gater.update_history(-20.0, 0.0)

        raw_flow = FlowResult(
            valid=True,
            dx_viewport=20.0,
            dy_viewport=0.0,
            vx_viewport=600.0,
            vy_viewport=0.0,
            confidence=0.85,
            feature_count=10,
            fb_error_mean=0.20,
        )

        res = gater.evaluate_flow(raw_flow, pred_vx=0.0, pred_vy=0.0)

        assert res.jitter_score > 15.0
        assert res.weight < 0.15
        assert res.gate_reason == "HIGH_JITTER"

    def test_clean_figure8_flow_remains_useful(self) -> None:
        """Smooth orbital trajectory (Figure-8 curvature) maintains low jitter score and high weight."""
        gater = AdaptiveFlowGater(dt=1.0 / 30.0)

        # Smooth curved progression without high-frequency sign flipping
        angles = np.linspace(0, np.pi / 2, 6)
        for a in angles:
            dx = float(4.0 * np.cos(a))
            dy = float(3.0 * np.sin(a))
            gater.update_history(dx, dy)

        raw_flow = FlowResult(
            valid=True,
            dx_viewport=float(4.0 * np.cos(np.pi / 2)),
            dy_viewport=float(3.0 * np.sin(np.pi / 2)),
            vx_viewport=0.0,
            vy_viewport=90.0,
            confidence=0.90,
            feature_count=10,
            fb_error_mean=0.20,
        )

        res = gater.evaluate_flow(raw_flow, pred_vx=2.0, pred_vy=88.0)
        assert res.jitter_score < 4.0
        assert res.weight >= 0.65
        assert res.gate_reason == "GOOD_FLOW"

    def test_fast_target_flow_remains_useful(self) -> None:
        """High-speed constant-velocity target maintains low acceleration step and high weight."""
        gater = AdaptiveFlowGater(dt=1.0 / 30.0)

        for _ in range(5):
            gater.update_history(8.0, 4.0)  # 240 px/s, 120 px/s

        raw_flow = FlowResult(
            valid=True,
            dx_viewport=8.0,
            dy_viewport=4.0,
            vx_viewport=240.0,
            vy_viewport=120.0,
            confidence=0.92,
            feature_count=12,
            fb_error_mean=0.18,
        )

        res = gater.evaluate_flow(raw_flow, pred_vx=238.0, pred_vy=121.0)
        assert res.jitter_score < 1.0
        assert res.weight >= 0.75
        assert res.gate_reason == "GOOD_FLOW"

    def test_invalid_flow_weight_zero(self) -> None:
        """Invalid flow returns weight 0.0 and INVALID_FLOW / NO_FLOW."""
        gater = AdaptiveFlowGater()
        res_none = gater.evaluate_flow(None)
        assert res_none.weight == 0.0
        assert not res_none.valid
        assert res_none.gate_reason == "NO_FLOW"

        res_invalid = gater.evaluate_flow(FlowResult(valid=False))
        assert res_invalid.weight == 0.0
        assert not res_invalid.valid
        assert res_invalid.gate_reason == "INVALID_FLOW"

    def test_weight_zero_exact_fallback_behavior(self) -> None:
        """
        When optical flow has weight 0.0, IMM update state and covariance match
        the exact behavior of an IMM update with flow=None.
        """
        cfg = default_config()

        imm1 = IMMTracker(cfg, dt=1.0 / 30.0)
        imm2 = IMMTracker(cfg, dt=1.0 / 30.0)

        imm1.init_track(100.0, 100.0, vx=10.0, vy=5.0, confidence=0.8)
        imm2.init_track(100.0, 100.0, vx=10.0, vy=5.0, confidence=0.8)

        imm1.predict()
        imm2.predict()

        # Update imm1 with no flow
        state1 = imm1.update(102.0, 101.0, score=0.9, flow=None)

        # Update imm2 with zero-weight flow (invalid or gated)
        zero_flow = FlowResult(valid=False)
        state2 = imm2.update(102.0, 101.0, score=0.9, flow=zero_flow)

        assert pytest.approx(state1.x, abs=1e-6) == state2.x
        assert pytest.approx(state1.y, abs=1e-6) == state2.y
        assert pytest.approx(state1.vx, abs=1e-6) == state2.vx
        assert pytest.approx(state1.vy, abs=1e-6) == state2.vy
        assert pytest.approx(imm1.mu, abs=1e-6) == imm2.mu

    def test_weight_bounded_in_zero_one(self) -> None:
        """Flow weight is strictly bounded in [0.0, 1.0] across wide range of extreme values."""
        gater = AdaptiveFlowGater()

        for fb in [0.0, 0.5, 2.0, 10.0]:
            for fc in [0, 1, 5, 20, 100]:
                for conf in [0.0, 0.5, 1.0, 2.0]:
                    raw_flow = FlowResult(
                        valid=True,
                        dx_viewport=5.0,
                        dy_viewport=5.0,
                        vx_viewport=150.0,
                        vy_viewport=150.0,
                        confidence=conf,
                        feature_count=fc,
                        fb_error_mean=fb,
                    )
                    res = gater.evaluate_flow(raw_flow, pred_vx=0.0, pred_vy=0.0)
                    assert 0.0 <= res.weight <= 1.0
                    assert 0.0 <= res.quality <= 1.0

    def test_deterministic_behavior_fixed_inputs(self) -> None:
        """Gater produces 100% deterministic identical outputs given identical inputs."""
        gater1 = AdaptiveFlowGater(dt=1.0 / 30.0)
        gater2 = AdaptiveFlowGater(dt=1.0 / 30.0)

        raw = FlowResult(
            valid=True,
            dx_viewport=3.0,
            dy_viewport=1.5,
            vx_viewport=90.0,
            vy_viewport=45.0,
            confidence=0.85,
            feature_count=8,
            fb_error_mean=0.3,
        )

        res1 = gater1.evaluate_flow(raw, pred_vx=88.0, pred_vy=46.0)
        res2 = gater2.evaluate_flow(raw, pred_vx=88.0, pred_vy=46.0)

        assert res1.weight == res2.weight
        assert res1.quality == res2.quality
        assert res1.innovation == res2.innovation
        assert res1.jitter_score == res2.jitter_score
        assert res1.gate_reason == res2.gate_reason
