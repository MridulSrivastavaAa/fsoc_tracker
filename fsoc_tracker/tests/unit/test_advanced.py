"""
tests/unit/test_advanced.py
===========================
Unit & Integration Tests for Phase 7: Custom Feature
Adaptive Atmospheric Turbulence Compensator & Predictive Scintillation Mitigation (ATAC-PSM).
"""
import pytest
import numpy as np

from fsoc.core.config import default_config
from fsoc.core.types import CameraCommand
from fsoc.core.engine import ClosedLoopEngine
from fsoc.advanced.turbulence_estimator import ScintillationEstimator, TurbulenceRegime
from fsoc.advanced.adaptive_controller import AdaptiveTurbulenceCompensator


# ===========================================================================
# 1. Scintillation & Fried Parameter Estimator Tests
# ===========================================================================

class TestScintillationEstimator:
    def test_constant_intensity_weak_regime(self) -> None:
        """Constant intensity should have zero variance and weak regime."""
        estimator = ScintillationEstimator()
        for _ in range(20):
            diag = estimator.update(200.0)

        assert diag["scintillation_index"] < 0.05
        assert diag["regime"] == TurbulenceRegime.WEAK.value
        assert diag["fried_parameter_cm"] >= 15.0
        assert diag["is_deep_fade"] is False

    def test_fluctuating_intensity_strong_regime(self) -> None:
        """Highly fluctuating intensity should yield high scintillation index."""
        estimator = ScintillationEstimator()
        # Feed alternating high and low intensities (deep scintillation)
        rng = np.random.RandomState(42)
        for _ in range(25):
            val = float(rng.choice([30.0, 220.0]))
            diag = estimator.update(val)

        assert diag["scintillation_index"] > 0.3
        assert diag["regime"] in (TurbulenceRegime.MODERATE.value, TurbulenceRegime.STRONG.value)
        assert diag["fried_parameter_cm"] < 15.0

    def test_deep_fade_detection(self) -> None:
        estimator = ScintillationEstimator()
        # Prime buffer with high average
        for _ in range(15):
            estimator.update(200.0)

        # Severe fade drops to 20 (< 35% of 200)
        diag = estimator.update(20.0)
        assert diag["is_deep_fade"] is True


# ===========================================================================
# 2. Adaptive Controller & Jerk Mitigation Tests
# ===========================================================================

class TestAdaptiveController:
    def test_adaptive_r_scaling(self) -> None:
        comp = AdaptiveTurbulenceCompensator()
        scale_weak = comp.compute_adaptive_r_scale(0.05)
        scale_strong = comp.compute_adaptive_r_scale(1.2)

        assert scale_weak < scale_strong
        assert scale_strong > 1.5

    def test_actuator_low_pass_filtering(self) -> None:
        """Verify command filter suppresses high-frequency jitter."""
        comp = AdaptiveTurbulenceCompensator()
        # Alternate fast +5 and -5 deg/s commands
        cmd_pos = CameraCommand(pan_rate_deg_per_s=5.0, tilt_rate_deg_per_s=0.0)
        cmd_neg = CameraCommand(pan_rate_deg_per_s=-5.0, tilt_rate_deg_per_s=0.0)

        filt1 = comp.filter_actuator_command(cmd_pos, TurbulenceRegime.STRONG)
        filt2 = comp.filter_actuator_command(cmd_neg, TurbulenceRegime.STRONG)

        # Filtered rate should be smoothed, not jumping straight to -5
        assert filt2.pan_rate_deg_per_s > -4.5

    def test_process_frame_integration(self) -> None:
        comp = AdaptiveTurbulenceCompensator()
        raw_cmd = CameraCommand(2.0, 1.0)
        filt_cmd, r_scale, diag = comp.process_frame(210.0, raw_cmd)

        assert isinstance(filt_cmd, CameraCommand)
        assert r_scale >= 1.0
        assert "scintillation_index" in diag


# ===========================================================================
# 3. Closed-Loop Engine Phase 7 Integration Tests
# ===========================================================================

def test_engine_closed_loop_with_turbulence_compensation() -> None:
    """Verify ClosedLoopEngine operates with Phase 7 compensator active."""
    cfg = default_config()
    cfg.pipeline.duration_s = 1.0
    cfg.advanced.enabled = True

    engine = ClosedLoopEngine(cfg)
    summary = engine.run(max_frames=60)

    assert summary.duration_s > 0.0
    assert hasattr(engine, "last_turbulence_diag")
    assert "scintillation_index" in engine.last_turbulence_diag
    # Ensure tracking error converges under ISRO R14 limit (<= 10 px)
    assert summary.error_mean_px <= 10.0
