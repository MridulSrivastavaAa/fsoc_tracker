"""
src/fsoc/benchmarks/metrics.py
==============================
Quantitative Evaluation & KPI Calculator for FSOC Benchmark Runs.
Computes all ISRO Problem Statement 26169 KPIs:
- R13: Initial Target Acquisition Time (s)
- R14: Coarse Tracking Error (Mean, RMSE, Max in pixels)
- R15: Target Loss Rate & Lock Retention (%)
- R22: Real-time throughput (Mean FPS, P95 latency ms)
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Optional
import json
import numpy as np

from ..core.types import FrameMetrics, RunSummary


@dataclass
class ScenarioKPIs:
    """Quantitative performance indicators for a single benchmark scenario."""
    scenario_name: str
    duration_s: float
    total_frames: int
    acquisition_time_s: Optional[float]
    reacquisition_count: int
    reacquisition_time_mean_s: Optional[float]
    error_mean_px: float
    error_rmse_px: float
    error_max_px: float
    error_std_px: float
    lock_retention_pct: float
    target_loss_pct: float
    proc_ms_mean: float
    proc_ms_p95: float
    fps_effective: float
    jitter_metric_px: float
    passed_r13: bool   # Acquisition <= 2.0s
    passed_r14: bool   # Tracking error <= 10.0 px
    passed_r15: bool   # Target loss < 5%
    passed_r22: bool   # Processing latency <= 33.3 ms (>= 30 FPS)
    all_passed: bool

    def to_dict(self) -> dict:
        return asdict(self)


class MetricsEvaluator:
    """
    Analyzes raw FrameMetrics logs from ClosedLoopEngine and computes
    standardized evaluation benchmarks.
    """
    @staticmethod
    def evaluate(
        scenario_name: str,
        history: list[FrameMetrics],
        acquisition_time_s: Optional[float] = None,
        reacquisition_times: Optional[list[float]] = None,
    ) -> ScenarioKPIs:
        """
        Compute complete KPI breakdown from frame metrics history.
        """
        if not history:
            return ScenarioKPIs(
                scenario_name=scenario_name,
                duration_s=0.0,
                total_frames=0,
                acquisition_time_s=None,
                reacquisition_count=0,
                reacquisition_time_mean_s=None,
                error_mean_px=0.0,
                error_rmse_px=0.0,
                error_max_px=0.0,
                error_std_px=0.0,
                lock_retention_pct=0.0,
                target_loss_pct=100.0,
                proc_ms_mean=0.0,
                proc_ms_p95=0.0,
                fps_effective=0.0,
                jitter_metric_px=0.0,
                passed_r13=False,
                passed_r14=False,
                passed_r15=False,
                passed_r22=False,
                all_passed=False,
            )

        total_frames = len(history)
        duration_s = float(history[-1].timestamp_s - history[0].timestamp_s)

        # Processing time statistics
        proc_times = [m.proc_ms for m in history]
        proc_mean = float(np.mean(proc_times))
        proc_p95 = float(np.percentile(proc_times, 95))
        fps_eff = float(1000.0 / max(0.1, proc_mean))

        # Lock retention & loss rates
        locked_frames = [m for m in history if m.locked]
        lock_pct = float(100.0 * len(locked_frames) / total_frames)
        lost_frames = [m for m in history if m.state in ("LOST", "REACQUIRE")]
        loss_pct = float(100.0 * len(lost_frames) / total_frames)

        # Tracking error statistics (on locked frames, or all frames with error)
        errors = [m.error_px for m in locked_frames if m.error_px is not None]
        if not errors:
            errors = [m.error_px for m in history if m.error_px is not None]

        if errors:
            err_arr = np.array(errors, dtype=np.float64)
            err_mean = float(np.mean(err_arr))
            err_rmse = float(np.sqrt(np.mean(np.square(err_arr))))
            err_max = float(np.max(err_arr))
            err_std = float(np.std(err_arr))
        else:
            err_mean = 0.0
            err_rmse = 0.0
            err_max = 0.0
            err_std = 0.0

        # Frame-to-frame tracking jitter
        jitter_px = 0.0
        if len(errors) > 1:
            diffs = np.abs(np.diff(errors))
            jitter_px = float(np.mean(diffs))

        # Reacquisitions
        reacqs = reacquisition_times or []
        reacq_count = len(reacqs)
        reacq_mean = float(np.mean(reacqs)) if reacqs else None

        # ISRO Requirements verification
        r13 = (acquisition_time_s is not None and acquisition_time_s <= 2.0) or (acquisition_time_s is None and lock_pct > 80.0)
        r14 = err_mean <= 10.0 and err_rmse <= 12.0
        r15 = loss_pct < 5.0 or lock_pct >= 90.0
        r22 = proc_mean <= 33.3 and proc_p95 <= 40.0
        all_passed = bool(r13 and r14 and r15 and r22)

        return ScenarioKPIs(
            scenario_name=scenario_name,
            duration_s=duration_s,
            total_frames=total_frames,
            acquisition_time_s=acquisition_time_s,
            reacquisition_count=reacq_count,
            reacquisition_time_mean_s=reacq_mean,
            error_mean_px=err_mean,
            error_rmse_px=err_rmse,
            error_max_px=err_max,
            error_std_px=err_std,
            lock_retention_pct=lock_pct,
            target_loss_pct=loss_pct,
            proc_ms_mean=proc_mean,
            proc_ms_p95=proc_p95,
            fps_effective=fps_eff,
            jitter_metric_px=jitter_px,
            passed_r13=r13,
            passed_r14=r14,
            passed_r15=r15,
            passed_r22=r22,
            all_passed=all_passed,
        )

    @staticmethod
    def export_json(kpis: list[ScenarioKPIs], filepath: str) -> None:
        """Export benchmark results to JSON file."""
        data = [k.to_dict() for k in kpis]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
