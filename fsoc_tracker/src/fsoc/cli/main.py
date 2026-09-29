"""
src/fsoc/cli/main.py
====================
Unified Command-Line Interface (CLI) for FSOC Virtual Camera Tracking System.
Commands:
  python -m fsoc.cli benchmark --type 1
  python -m fsoc.cli benchmark --type 2 --video path/to/video.mp4
  python -m fsoc.cli benchmark --type all
  python -m fsoc.cli run --duration 10.0 --config configs/default.yaml
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from ..core.config import load_config, default_config
from ..core.engine import ClosedLoopEngine
from ..benchmarks.runner import BenchmarkRunner
from ..benchmarks.metrics import ScenarioKPIs


def print_kpi_table(kpis: list[ScenarioKPIs]) -> None:
    """Print clean ASCII table of benchmark evaluation results."""
    print("\n" + "=" * 115)
    print(f"{'Scenario Name':<32} | {'Dur(s)':<6} | {'Err Mean':<8} | {'RMSE':<6} | {'Max Err':<7} | {'Lock %':<6} | {'FPS':<6} | {'P95 ms':<6} | {'Status':<6}")
    print("-" * 115)
    for k in kpis:
        status = "PASS" if k.all_passed else "FAIL"
        print(
            f"{k.scenario_name:<32} | "
            f"{k.duration_s:<6.1f} | "
            f"{k.error_mean_px:<8.2f} | "
            f"{k.error_rmse_px:<6.2f} | "
            f"{k.error_max_px:<7.2f} | "
            f"{k.lock_retention_pct:<6.1f} | "
            f"{k.fps_effective:<6.1f} | "
            f"{k.proc_ms_p95:<6.1f} | "
            f"{status:<6}"
        )
    print("=" * 115 + "\n")


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Handle `benchmark` subcommand."""
    runner = BenchmarkRunner(output_dir=args.output)
    print(f"\n[FSOC Tracker] Launching Automated Benchmark Evaluation Suite (Type: {args.type})...")

    if args.type == "1":
        results = runner.run_benchmark_1(duration_s=args.duration)
        print_kpi_table(results)
    elif args.type == "2":
        result = runner.run_benchmark_2(video_path=args.video, max_frames=int(args.duration * 30))
        print_kpi_table([result])
    else:  # all
        all_results = runner.run_all(duration_s=args.duration)
        combined = all_results["benchmark_1"] + all_results["benchmark_2"]
        print_kpi_table(combined)

    print(f"[FSOC Tracker] Evaluation results saved to: {args.output}/benchmark_results.json\n")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Handle `run` subcommand for single closed-loop simulation."""
    cfg = load_config(args.config) if args.config else default_config()
    cfg.pipeline.duration_s = args.duration

    print(f"\n[FSOC Tracker] Running Closed-Loop Tracking Simulation ({args.duration}s)...")
    engine = ClosedLoopEngine(cfg)
    summary = engine.run(max_frames=int(args.duration * cfg.pipeline.fps))

    print("\n--- Simulation Summary ---")
    print(f"Duration:            {summary.duration_s:.2f} s")
    print(f"Mean Tracking Error: {summary.error_mean_px:.2f} px")
    print(f"RMSE Error:          {summary.error_rmse_px:.2f} px")
    print(f"Max Tracking Error:  {summary.error_max_px:.2f} px")
    print(f"Lock Retention:      {summary.lock_retention_pct:.1f} %")
    print(f"Acquisition Time:    {summary.acquisition_time_s or 0.0:.3f} s")
    print(f"Mean Loop Latency:   {summary.proc_ms_mean:.2f} ms ({summary.fps_mean:.1f} FPS)")
    print(f"P95 Latency:         {summary.proc_ms_p95:.2f} ms")
    print("--------------------------\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct command line parser."""
    parser = argparse.ArgumentParser(
        prog="fsoc",
        description="ISRO PS 26169 AI-Based Virtual Camera Tracking System",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Benchmark parser
    p_bench = subparsers.add_parser("benchmark", help="Run automated benchmark evaluations")
    p_bench.add_argument(
        "--type", "-t", choices=["1", "2", "all"], default="all",
        help="Benchmark type: 1 (Simulated), 2 (Video file), or all",
    )
    p_bench.add_argument("--duration", "-d", type=float, default=2.0, help="Run duration per scenario in seconds")
    p_bench.add_argument("--video", "-i", type=str, default=None, help="Input .mp4 video for Benchmark-2")
    p_bench.add_argument("--output", "-o", type=str, default="benchmark_results", help="Output directory for results")

    # Run parser
    p_run = subparsers.add_parser("run", help="Run a single closed-loop simulation")
    p_run.add_argument("--config", "-c", type=str, default=None, help="Path to custom config YAML")
    p_run.add_argument("--duration", "-d", type=float, default=3.0, help="Simulation duration in seconds")

    # GUI parser
    p_gui = subparsers.add_parser("gui", help="Launch interactive desktop GUI application")
    p_gui.add_argument(
        "--mode", "-m", choices=["3d", "2d"], default="3d",
        help="Desktop GUI mode: 3d (3D Earth & Orbit Visualizer) or 2d (Tactical HUD Workstation)",
    )
    p_gui.add_argument("--config", "-c", type=str, default=None, help="Path to custom config YAML")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "benchmark":
        return cmd_benchmark(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "gui":
        if getattr(args, "mode", "3d") == "3d":
            from ..gui.app_3d import launch_3d_desktop
            launch_3d_desktop()
        else:
            from ..gui.app import launch_gui
            cfg = load_config(args.config) if args.config else default_config()
            launch_gui(cfg)
        return 0
    else:
        parser.print_help()
        return 0



if __name__ == "__main__":
    sys.exit(main())
