"""
src/fsoc/benchmarks/logger.py
==============================
ISRO PS 26169 — Mandatory Performance Logging & Auto-Report Generation.

Deliverables fulfilled (from PS):
  R27 - Auto performance log: duration, FPS, acquisition time, avg/max error,
        lock retention %, processing time.
  R30 - Per-frame centroiding error CSV (Benchmark-1).
  R29 - Per-frame beacon position CSV for .mp4 video mode (Benchmark-2):
        output columns: frame, x, y, confidence, state.

Output file layout:
  benchmark_results/
    ├── benchmark_results.json          ← R27: full KPI summary (JSON)
    ├── frame_log_<scenario>.csv        ← R30: per-frame detail (Benchmark-1)
    ├── benchmark_2_tracking.csv        ← R29: video-mode output
    └── run_report.txt                  ← Human-readable summary report
"""
from __future__ import annotations
import csv
import json
import datetime
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from ..core.types import FrameMetrics, RunSummary
from .metrics import ScenarioKPIs


# ---------------------------------------------------------------------------
# CSV column schemas (from PS 26169 design contract)
# ---------------------------------------------------------------------------

# R30: Benchmark-1 per-frame centroiding error log
_B1_CSV_HEADERS = [
    "frame", "timestamp_s", "state",
    "est_x", "est_y", "gt_x", "gt_y",
    "centroid_error_px",          # required by PS: centroiding error per frame
    "confidence", "locked",
    "proc_ms", "pan_deg", "tilt_deg",
]

# R29: Benchmark-2 video-mode per-frame output
_B2_CSV_HEADERS = [
    "frame", "x", "y", "confidence", "state",
]

# R27: JSON summary keys (all fields from ISRO KPI table)
_SUMMARY_KEYS_ORDERED = [
    "scenario_name",
    "duration_s",
    "total_frames",
    "acquisition_time_s",
    "reacquisition_count",
    "reacquisition_time_mean_s",
    "error_mean_px",
    "error_rmse_px",
    "error_max_px",
    "error_std_px",
    "lock_retention_pct",
    "target_loss_pct",
    "proc_ms_mean",
    "proc_ms_p95",
    "fps_effective",
    "jitter_metric_px",
    "passed_r13",
    "passed_r14",
    "passed_r15",
    "passed_r22",
    "all_passed",
]


class PerformanceLogger:
    """
    Handles all mandatory file I/O for ISRO PS 26169 performance logging.

    Usage:
        logger = PerformanceLogger(output_dir="benchmark_results")
        logger.write_b1_frame_log("scenario_name", engine.metrics_history)
        logger.write_b2_tracking_csv(metrics_history)
        logger.write_json_summary(all_kpis)
        logger.write_text_report(all_kpis)
    """

    def __init__(self, output_dir: str = "benchmark_results") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # R30 — Benchmark-1: per-frame centroiding error CSV
    # ------------------------------------------------------------------

    def write_b1_frame_log(
        self,
        scenario_name: str,
        history: list[FrameMetrics],
    ) -> Path:
        """
        Write per-frame centroiding error log for Benchmark-1 (R30).

        Columns: frame, timestamp_s, state, est_x, est_y, gt_x, gt_y,
                 centroid_error_px, confidence, locked, proc_ms, pan_deg, tilt_deg
        """
        # Sanitise scenario name for filesystem
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in scenario_name)
        out_path = self.output_dir / f"frame_log_{safe_name}.csv"

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_B1_CSV_HEADERS)
            for m in history:
                writer.writerow([
                    m.frame_index,
                    f"{m.timestamp_s:.4f}",
                    m.state,
                    f"{m.est_x:.3f}" if m.est_x is not None else "",
                    f"{m.est_y:.3f}" if m.est_y is not None else "",
                    f"{m.gt_x:.3f}" if m.gt_x is not None else "",
                    f"{m.gt_y:.3f}" if m.gt_y is not None else "",
                    f"{m.error_px:.4f}" if m.error_px is not None else "",
                    f"{m.confidence:.4f}",
                    int(m.locked),
                    f"{m.proc_ms:.3f}",
                    f"{m.pan_deg:.4f}",
                    f"{m.tilt_deg:.4f}",
                ])

        return out_path

    # ------------------------------------------------------------------
    # R29 — Benchmark-2: video-mode tracking output CSV
    # ------------------------------------------------------------------

    def write_b2_tracking_csv(
        self,
        history: list[FrameMetrics],
        filename: str = "benchmark_2_tracking.csv",
    ) -> Path:
        """
        Write Benchmark-2 video-mode output (R29).

        Output columns (as per PS 26169 contract):
            frame, x, y, confidence, state
        """
        out_path = self.output_dir / filename

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_B2_CSV_HEADERS)
            for m in history:
                writer.writerow([
                    m.frame_index,
                    f"{m.est_x:.3f}" if m.est_x is not None else "",
                    f"{m.est_y:.3f}" if m.est_y is not None else "",
                    f"{m.confidence:.4f}",
                    m.state,
                ])

        return out_path

    # ------------------------------------------------------------------
    # R27 — Full JSON KPI summary
    # ------------------------------------------------------------------

    def write_json_summary(
        self,
        kpis: list[ScenarioKPIs],
        filename: str = "benchmark_results.json",
    ) -> Path:
        """
        Write complete benchmark KPI summary to JSON (R27).
        Includes all ISRO-specified metrics: duration, FPS, acquisition time,
        avg/max error, lock retention %, processing time.
        """
        out_path = self.output_dir / filename

        report = {
            "generated_at": datetime.datetime.now().isoformat(),
            "isro_ps_id": "26169",
            "system": "AI-Based Virtual Camera Tracking System — FSOC Coarse Alignment",
            "scenarios": [],
            "overall": {},
        }

        all_passed_count = 0
        for kpi in kpis:
            d = asdict(kpi)
            # Ensure ordered keys in output
            ordered = {k: d[k] for k in _SUMMARY_KEYS_ORDERED if k in d}
            ordered.update({k: v for k, v in d.items() if k not in _SUMMARY_KEYS_ORDERED})
            report["scenarios"].append(ordered)
            if kpi.all_passed:
                all_passed_count += 1

        # Aggregate summary across all scenarios
        if kpis:
            import numpy as np
            report["overall"] = {
                "total_scenarios": len(kpis),
                "scenarios_passed": all_passed_count,
                "pass_rate_pct": round(100.0 * all_passed_count / len(kpis), 1),
                "mean_error_px": round(float(np.mean([k.error_mean_px for k in kpis])), 3),
                "mean_rmse_px": round(float(np.mean([k.error_rmse_px for k in kpis])), 3),
                "mean_lock_retention_pct": round(float(np.mean([k.lock_retention_pct for k in kpis])), 1),
                "mean_fps": round(float(np.mean([k.fps_effective for k in kpis])), 1),
                "mean_acquisition_time_s": round(
                    float(np.mean([k.acquisition_time_s for k in kpis if k.acquisition_time_s is not None])), 3
                ) if any(k.acquisition_time_s for k in kpis) else None,
                "isro_r13_passed": all(k.passed_r13 for k in kpis),
                "isro_r14_passed": all(k.passed_r14 for k in kpis),
                "isro_r15_passed": all(k.passed_r15 for k in kpis),
                "isro_r22_passed": all(k.passed_r22 for k in kpis),
            }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

        return out_path

    # ------------------------------------------------------------------
    # Human-readable text report
    # ------------------------------------------------------------------

    def write_text_report(
        self,
        kpis: list[ScenarioKPIs],
        filename: str = "run_report.txt",
    ) -> Path:
        """
        Write human-readable plain-text performance report.
        Suitable for including in submission documentation.
        """
        out_path = self.output_dir / filename
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines: list[str] = []
        lines.append("=" * 80)
        lines.append("ISRO / SAC PS 26169 — FSOC VIRTUAL CAMERA TRACKING SYSTEM")
        lines.append("AUTOMATED PERFORMANCE EVALUATION REPORT")
        lines.append(f"Generated: {now}")
        lines.append("=" * 80)
        lines.append("")

        for kpi in kpis:
            status = "✓ PASS" if kpi.all_passed else "✗ FAIL"
            lines.append(f"Scenario: {kpi.scenario_name}  [{status}]")
            lines.append("-" * 60)
            lines.append(f"  Duration:               {kpi.duration_s:.2f} s  ({kpi.total_frames} frames)")
            lines.append(f"  Acquisition Time:       {kpi.acquisition_time_s:.3f} s  (spec ≤ 2.0 s)  [{'PASS' if kpi.passed_r13 else 'FAIL'}]"
                         if kpi.acquisition_time_s else
                         f"  Acquisition Time:       N/A  [{'PASS' if kpi.passed_r13 else 'FAIL'}]")
            lines.append(f"  Mean Tracking Error:    {kpi.error_mean_px:.2f} px  (spec ≤ 10 px)  [{'PASS' if kpi.passed_r14 else 'FAIL'}]")
            lines.append(f"  RMSE Tracking Error:    {kpi.error_rmse_px:.2f} px")
            lines.append(f"  Max Tracking Error:     {kpi.error_max_px:.2f} px")
            lines.append(f"  Lock Retention:         {kpi.lock_retention_pct:.1f} %  (spec > 95 %)")
            lines.append(f"  Target Loss Rate:       {kpi.target_loss_pct:.1f} %  (spec < 5 %)  [{'PASS' if kpi.passed_r15 else 'FAIL'}]")
            lines.append(f"  Mean Processing Time:   {kpi.proc_ms_mean:.2f} ms")
            lines.append(f"  P95 Processing Time:    {kpi.proc_ms_p95:.2f} ms")
            lines.append(f"  Effective FPS:          {kpi.fps_effective:.1f}  (spec ≥ 20)  [{'PASS' if kpi.passed_r22 else 'FAIL'}]")
            if kpi.reacquisition_count:
                lines.append(f"  Re-acquisitions:        {kpi.reacquisition_count} events"
                             + (f"  (mean {kpi.reacquisition_time_mean_s:.3f} s)" if kpi.reacquisition_time_mean_s else ""))
            lines.append("")

        lines.append("=" * 80)
        lines.append("ISRO REQUIREMENT VERIFICATION SUMMARY")
        lines.append("-" * 80)

        if kpis:
            import numpy as np
            all_r13 = all(k.passed_r13 for k in kpis)
            all_r14 = all(k.passed_r14 for k in kpis)
            all_r15 = all(k.passed_r15 for k in kpis)
            all_r22 = all(k.passed_r22 for k in kpis)
            lines.append(f"  R13 – Acquisition time ≤ 2 s:       {'PASS' if all_r13 else 'FAIL'}")
            lines.append(f"  R14 – Tracking error ≤ 10 px:       {'PASS' if all_r14 else 'FAIL'}")
            lines.append(f"  R15 – Target loss rate < 5 %:       {'PASS' if all_r15 else 'FAIL'}")
            lines.append(f"  R22 – Processing speed ≥ 20 FPS:    {'PASS' if all_r22 else 'FAIL'}")
            passed = sum([all_r13, all_r14, all_r15, all_r22])
            lines.append(f"\n  Overall: {passed}/4 requirements met across all scenarios.")
        lines.append("=" * 80)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return out_path
