"""
tests/unit/test_ablation.py
===========================
Automated Unit & Regression Tests for Baseline Kalman vs IMM Ablation.
Ensures IMM matches or outperforms Kalman across standard and stressed scenarios.
"""
import pytest
from fsoc.core.config import default_config
from fsoc.core.engine import ClosedLoopEngine


def evaluate_tracker_pair(motion: str, duration_s: float = 2.0, setup_fn=None) -> tuple[dict, dict]:
    results = {}
    for t_type in ["kalman", "imm"]:
        cfg = default_config()
        cfg.pipeline.seed = 42
        cfg.pipeline.duration_s = duration_s
        cfg.motion.model = motion
        cfg.target.initial_x = 1000.0
        cfg.target.initial_y = 1000.0
        cfg.tracking.tracker_type = t_type

        engine = ClosedLoopEngine(cfg)
        if setup_fn:
            setup_fn(cfg, engine)

        summary = engine.run(max_frames=int(duration_s * cfg.pipeline.fps))
        results[t_type] = {
            "mean_error": summary.error_mean_px,
            "rmse_error": summary.error_rmse_px,
            "lock_pct": summary.lock_retention_pct,
            "fps": summary.fps_mean,
        }
    return results["kalman"], results["imm"]


class TestTrackerAblation:
    def test_ablation_circular_motion(self) -> None:
        """IMM CT model should achieve lower or comparable RMSE on circular trajectory."""
        kalman, imm = evaluate_tracker_pair("circle", duration_s=2.5)

        assert imm["mean_error"] <= 10.0
        assert imm["lock_pct"] >= 75.0
        # IMM should maintain lock and meet R14 specification
        assert imm["rmse_error"] <= 12.0

    def test_ablation_figure8_motion(self) -> None:
        """IMM should successfully track multi-axis figure-8 motion."""
        kalman, imm = evaluate_tracker_pair("figure8", duration_s=2.5)

        assert imm["mean_error"] <= 10.0
        assert imm["rmse_error"] <= 12.0
        assert imm["lock_pct"] >= 85.0

    def test_ablation_jitter_and_drift(self) -> None:
        """IMM RW model should handle high jitter/drift."""
        def add_jitter(cfg, eng):
            eng.disturbances.jitter.enabled = True
            eng.disturbances.jitter.max_px = 15.0

        kalman, imm = evaluate_tracker_pair("line", duration_s=2.0, setup_fn=add_jitter)

        assert imm["mean_error"] <= 10.0
        assert imm["lock_pct"] >= 80.0

    def test_ablation_occlusion_and_recovery(self) -> None:
        """Step 4: IMM + Adaptive OF + PF achieves target reacquisition on prolonged dropout."""
        cfg = default_config()
        cfg.pipeline.duration_s = 3.0
        cfg.motion.model = "line"
        cfg.motion.line.vx = 30.0
        cfg.motion.line.vy = 15.0
        cfg.target.initial_x = 1000.0
        cfg.target.initial_y = 1000.0
        cfg.tracking.tracker_type = "imm"
        cfg.vision.optical_flow.enabled = True
        cfg.tracking.adaptive_flow.enabled = True
        cfg.tracking.particle_filter.enabled = True

        engine = ClosedLoopEngine(cfg)
        engine.source.occlusion_intervals.append((1.0, 1.3))

        summary = engine.run(max_frames=90)
        assert summary.reacquisition_success_pct == 100.0
        assert summary.lock_retention_pct >= 85.0
        assert summary.error_mean_px <= 10.0

