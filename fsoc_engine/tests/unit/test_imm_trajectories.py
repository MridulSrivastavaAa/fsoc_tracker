"""
tests/unit/test_imm_trajectories.py
===================================
IMM Trajectory Tracking Performance Tests for ISRO PS 26169 Scenarios:
A. Straight-Line Motion
B. Circular Motion
C. Figure-8 Motion
D. Random Motion

Records:
- RMSE (px)
- Mean Error (px)
- P95 Error (px)
- Max Error (px)
- Throughput FPS
- Model Probabilities (CV, CT, RW) over time
"""
import numpy as np
import pytest

from fsoc.core.config import default_config
from fsoc.core.engine import ClosedLoopEngine


def run_trajectory_evaluation(motion_model: str, duration_s: float = 2.0, overrides: dict = None) -> dict:
    """Execute a closed-loop run and extract full error and IMM probability profiles."""
    cfg = default_config()
    cfg.pipeline.duration_s = duration_s
    cfg.target.initial_x = 1000.0
    cfg.target.initial_y = 1000.0
    cfg.target.brightness = 230
    cfg.motion.model = motion_model
    cfg.tracking.tracker_type = "imm"

    if overrides:
        for k, v in overrides.items():
            parts = k.split(".")
            obj = cfg
            for p in parts[:-1]:
                obj = getattr(obj, p)
            setattr(obj, parts[-1], v)

    engine = ClosedLoopEngine(cfg)
    max_frames = int(duration_s * cfg.pipeline.fps)
    summary = engine.run(max_frames=max_frames)

    locked_errors = [m.error_px for m in engine.metrics_history if m.locked and m.error_px is not None]
    all_errors = [m.error_px for m in engine.metrics_history if m.error_px is not None]
    err_eval = locked_errors if locked_errors else all_errors

    err_arr = np.array(err_eval, dtype=np.float64) if err_eval else np.array([0.0])
    mean_err = float(np.mean(err_arr))
    rmse_err = float(np.sqrt(np.mean(np.square(err_arr))))
    p95_err = float(np.percentile(err_arr, 95))
    max_err = float(np.max(err_arr))

    cv_probs = [m.prob_cv for m in engine.metrics_history if m.prob_cv > 0]
    ct_probs = [m.prob_ct for m in engine.metrics_history if m.prob_ct > 0]
    rw_probs = [m.prob_rw for m in engine.metrics_history if m.prob_rw > 0]

    return {
        "motion_model": motion_model,
        "duration_s": summary.duration_s,
        "total_frames": len(engine.metrics_history),
        "mean_error_px": summary.error_mean_px,
        "rmse_error_px": summary.error_rmse_px,
        "p95_error_px": p95_err,
        "max_error_px": summary.error_max_px,
        "fps_mean": summary.fps_mean,
        "lock_retention_pct": summary.lock_retention_pct,
        "mean_cv_prob": float(np.mean(cv_probs)) if cv_probs else 0.0,
        "mean_ct_prob": float(np.mean(ct_probs)) if ct_probs else 0.0,
        "mean_rw_prob": float(np.mean(rw_probs)) if rw_probs else 0.0,
    }


class TestIMMTrajectories:
    def test_trajectory_a_straight_line(self) -> None:
        """Trajectory A: Straight line target motion."""
        res = run_trajectory_evaluation("line", duration_s=2.0, overrides={"motion.line.vx": 50.0, "motion.line.vy": 25.0})

        # Verification vs PS R14 (Mean <= 10 px, RMSE <= 12 px)
        assert res["mean_error_px"] <= 10.0
        assert res["rmse_error_px"] <= 12.0
        assert res["lock_retention_pct"] >= 90.0
        # CV model should have highest mean probability on straight line
        assert res["mean_cv_prob"] >= 0.35

    def test_trajectory_b_circular(self) -> None:
        """Trajectory B: Circular target motion."""
        res = run_trajectory_evaluation("circle", duration_s=2.0)

        assert res["mean_error_px"] <= 10.0
        assert res["rmse_error_px"] <= 12.0
        assert res["lock_retention_pct"] >= 75.0
        # CT model should have elevated probability on circular turns
        assert res["mean_ct_prob"] >= 0.20

    def test_trajectory_c_figure8(self) -> None:
        """Trajectory C: Figure-8 target motion."""
        res = run_trajectory_evaluation("figure8", duration_s=2.0)

        assert res["mean_error_px"] <= 10.0
        assert res["rmse_error_px"] <= 12.0
        assert res["lock_retention_pct"] >= 85.0
        # CT and RW participate in turning and curvature transitions
        assert res["mean_ct_prob"] + res["mean_rw_prob"] >= 0.30

    def test_trajectory_d_random(self) -> None:
        """Trajectory D: Random stochastic target motion."""
        res = run_trajectory_evaluation("random", duration_s=2.0)

        assert res["mean_error_px"] <= 10.0
        assert res["rmse_error_px"] <= 12.0
        assert res["lock_retention_pct"] >= 80.0
        # RW participates strongly in sudden stochastic jumps
        assert res["mean_rw_prob"] >= 0.08
