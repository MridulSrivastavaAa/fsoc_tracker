"""
tests/unit/test_benchmarks.py
==============================
Unit & Integration Tests for Phase 5:
1. MetricsEvaluator statistical computations & JSON serialization
2. Benchmark-1 runner across multiple scenarios
3. Benchmark-2 pre-recorded video stream ingestion
4. Unified CLI entry point execution
"""
from pathlib import Path
import json
import pytest
import numpy as np

from fsoc.core.types import FrameMetrics
from fsoc.benchmarks.metrics import MetricsEvaluator, ScenarioKPIs
from fsoc.benchmarks.runner import BenchmarkRunner
from fsoc.cli.main import main, build_parser


# ===========================================================================
# 1. Metrics Evaluator Tests
# ===========================================================================

class TestMetricsEvaluator:
    def test_empty_history_returns_safe_defaults(self) -> None:
        kpi = MetricsEvaluator.evaluate("empty_test", [])
        assert kpi.total_frames == 0
        assert kpi.all_passed is False
        assert kpi.error_mean_px == 0.0

    def test_kpi_calculations_with_synthetic_metrics(self) -> None:
        history: list[FrameMetrics] = []
        for i in range(100):
            # 90 locked frames with 2.0 px error, 10 unlocked frames
            is_locked = i >= 10
            state = "TRACK" if is_locked else "SEARCH"
            err = 2.0 if is_locked else 15.0
            history.append(
                FrameMetrics(
                    frame_index=i,
                    timestamp_s=i * 0.0333,
                    state=state,
                    error_px=err,
                    confidence=0.9 if is_locked else 0.0,
                    locked=is_locked,
                    proc_ms=8.0,
                )
            )

        kpi = MetricsEvaluator.evaluate(
            "synthetic_eval",
            history,
            acquisition_time_s=0.333,
            reacquisition_times=[0.05],
        )

        assert kpi.total_frames == 100
        assert kpi.lock_retention_pct == 90.0
        assert abs(kpi.error_mean_px - 2.0) < 0.1  # Evaluated on locked frames
        assert abs(kpi.error_rmse_px - 2.0) < 0.1
        assert kpi.proc_ms_mean == pytest.approx(8.0)
        assert kpi.proc_ms_p95 == pytest.approx(8.0)
        assert kpi.fps_effective > 100.0
        assert kpi.passed_r13 is True
        assert kpi.passed_r14 is True
        assert kpi.passed_r22 is True

    def test_json_export(self, tmp_path: Path) -> None:
        kpi = ScenarioKPIs(
            scenario_name="test_export",
            duration_s=1.0,
            total_frames=30,
            acquisition_time_s=0.2,
            reacquisition_count=0,
            reacquisition_time_mean_s=None,
            error_mean_px=1.5,
            error_rmse_px=1.8,
            error_max_px=2.5,
            error_std_px=0.3,
            lock_retention_pct=95.0,
            target_loss_pct=5.0,
            proc_ms_mean=9.0,
            proc_ms_p95=11.0,
            fps_effective=111.0,
            jitter_metric_px=0.2,
            passed_r13=True,
            passed_r14=True,
            passed_r15=True,
            passed_r22=True,
            all_passed=True,
        )

        out_file = tmp_path / "test_kpis.json"
        MetricsEvaluator.export_json([kpi], str(out_file))

        assert out_file.exists()
        with open(out_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["scenario_name"] == "test_export"
        assert data[0]["all_passed"] is True


# ===========================================================================
# 2. Benchmark Runner Tests
# ===========================================================================

class TestBenchmarkRunner:
    def test_benchmark_1_execution(self, tmp_path: Path) -> None:
        """Verify Benchmark-1 executes scenarios and returns valid KPIs."""
        runner = BenchmarkRunner(output_dir=str(tmp_path))
        results = runner.run_benchmark_1(duration_s=1.0)

        assert len(results) == 5
        for kpi in results:
            assert kpi.duration_s > 0.0
            assert kpi.total_frames >= 25
            # Tracking error bounded across normal and stress scenarios
            assert kpi.error_mean_px <= 35.0
            assert kpi.proc_ms_mean < 45.0  # Real-time processing (ISRO R22: >= 20 FPS)
        # Ensure high-speed line or platform drift passes R14
        assert any(kpi.passed_r14 for kpi in results)

    def test_benchmark_2_execution(self, tmp_path: Path) -> None:
        """Verify Benchmark-2 synthetic video ingestion & tracking pipeline."""
        runner = BenchmarkRunner(output_dir=str(tmp_path))
        kpi = runner.run_benchmark_2(max_frames=30)

        assert kpi.scenario_name == "B2_Video_Stream_Evaluation"
        assert kpi.total_frames == 30
        assert kpi.proc_ms_mean < 45.0  # Real-time processing (ISRO R22: >= 20 FPS)
        assert kpi.lock_retention_pct > 50.0  # Successfully tracked

    def test_run_all(self, tmp_path: Path) -> None:
        """Verify run_all executes both benchmarks and saves JSON."""
        runner = BenchmarkRunner(output_dir=str(tmp_path))
        results = runner.run_all(duration_s=0.5)

        assert "benchmark_1" in results
        assert "benchmark_2" in results
        assert len(results["benchmark_1"]) == 5
        assert len(results["benchmark_2"]) == 1

        json_path = tmp_path / "benchmark_results.json"
        assert json_path.exists()


# ===========================================================================
# 3. CLI Command Tests
# ===========================================================================

class TestCLI:
    def test_parser_construction(self) -> None:
        parser = build_parser()
        assert parser.prog == "fsoc"

    def test_cli_benchmark_cmd(self, tmp_path: Path) -> None:
        ret = main(["benchmark", "--type", "1", "--duration", "0.5", "--output", str(tmp_path)])
        assert ret == 0

    def test_cli_run_cmd(self) -> None:
        ret = main(["run", "--duration", "0.5"])
        assert ret == 0
