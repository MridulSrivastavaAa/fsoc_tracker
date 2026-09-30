"""
src/fsoc/benchmarks/runner.py
=============================
Automated Benchmark Evaluation Suite for ISRO Problem Statement 26169.
Executes:
- Benchmark-1: Simulated scenarios across motion models & atmospheric disturbances
- Benchmark-2: Pre-recorded .mp4 video ingestion & bypass stream tracking

File outputs (mandatory ISRO deliverables):
  R27 - benchmark_results.json       : full KPI summary
  R29 - benchmark_2_tracking.csv     : per-frame x,y,confidence,state for video mode
  R30 - frame_log_<scenario>.csv     : per-frame centroiding error per B1 scenario
        run_report.txt               : human-readable performance report
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import os
import cv2
import numpy as np

from ..core.config import AppConfig, default_config
from ..core.engine import ClosedLoopEngine
from ..video.video_source import VideoFileSource
from ..vision.preprocess import VisionPreprocessor
from ..vision.detector import SpotDetector
from ..vision.cnn_verifier import BeaconVerifierCNN
from ..vision.optical_flow import OpticalFlowTracker
from ..tracking.kalman import KalmanTracker
from ..tracking.imm import IMMTracker
from ..tracking.state_machine import TrackingStateMachine
from ..core.types import FrameMetrics
from .metrics import MetricsEvaluator, ScenarioKPIs
from .logger import PerformanceLogger


class BenchmarkRunner:
    """
    Automated benchmark harness for FSOC tracker evaluation.
    All benchmark runs automatically save mandatory ISRO deliverable files to disk.
    """
    def __init__(self, output_dir: str = "benchmark_results") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = PerformanceLogger(str(self.output_dir))

    def run_benchmark_1(self, duration_s: float = 2.0) -> list[ScenarioKPIs]:
        """
        Execute Benchmark-1: Suite of 5 distinct simulated operational scenarios.
        """
        scenarios: list[tuple[str, str, dict]] = [
            ("B1_Scenario_1_Circular_Clear", "circle", {}),
            ("B1_Scenario_2_HighSpeed_Line", "line", {"motion.line.vx": 80.0, "motion.line.vy": 40.0}),
            ("B1_Scenario_3_Figure8_Noise", "figure8", {"disturbances.noise.gaussian_sigma": 10.0}),
            ("B1_Scenario_4_Atmosphere_Stress", "circle", {"disturbances.atmosphere.condition": "fog"}),
            ("B1_Scenario_5_Platform_Drift", "random", {"disturbances.platform.mode": "linear"}),
        ]

        results: list[ScenarioKPIs] = []

        for name, motion_type, overrides in scenarios:
            cfg = default_config()
            cfg.pipeline.duration_s = duration_s
            cfg.target.initial_x = 1000.0
            cfg.target.initial_y = 1000.0
            cfg.motion.model = motion_type

            if "motion.line.vx" in overrides:
                cfg.motion.line.vx = overrides["motion.line.vx"]
                cfg.motion.line.vy = overrides["motion.line.vy"]

            engine = ClosedLoopEngine(cfg)

            # Apply disturbance flags if specified
            if "disturbances.noise.gaussian_sigma" in overrides:
                engine.disturbances.gaussian.enabled = True
                engine.disturbances.gaussian.sigma = overrides["disturbances.noise.gaussian_sigma"]
            if "disturbances.atmosphere.condition" in overrides:
                engine.disturbances.atmosphere.set_condition(overrides["disturbances.atmosphere.condition"], strength=0.7)
            if "disturbances.platform.mode" in overrides:
                engine.disturbances.platform.enable_mode(overrides["disturbances.platform.mode"], max_shift=5.0)

            # Execute run
            max_frames = int(duration_s * cfg.pipeline.fps)
            summary = engine.run(max_frames=max_frames)

            kpi = MetricsEvaluator.evaluate(
                scenario_name=name,
                history=engine.metrics_history,
                acquisition_time_s=engine.state_machine.acquisition_time_s,
                reacquisition_times=engine.state_machine.reacquisition_times,
            )
            results.append(kpi)

            # R30 — Write per-frame centroiding error CSV for this scenario
            log_path = self.logger.write_b1_frame_log(name, engine.metrics_history)
            print(f"  [LOG] Per-frame CSV saved: {log_path}")

        return results

    def create_synthetic_test_video(
        self, video_path: Path, num_frames: int = 60, fps: int = 30
    ) -> Path:
        """
        Generate a synthetic benchmark .mp4 video if no external file is provided.
        Renders a moving Gaussian beacon spot across a 640x480 frame.
        """
        video_path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(video_path), fourcc, fps, (640, 480), isColor=False)

        cx, cy = 100.0, 150.0
        vx, vy = 100.0, 50.0
        dt = 1.0 / fps

        rng = np.random.RandomState(42)

        for f in range(num_frames):
            frame = np.full((480, 640), 20, dtype=np.uint8)
            # Add Gaussian noise
            noise = (rng.randn(480, 640) * 5.0).astype(np.int32)
            frame = np.clip(frame.astype(np.int32) + noise, 0, 255).astype(np.uint8)

            # Render Gaussian spot
            ix, iy = int(round(cx)), int(round(cy))
            cv2.circle(frame, (ix, iy), 6, 230, -1)

            writer.write(frame)
            cx += vx * dt
            cy += vy * dt

        writer.release()
        return video_path

    def run_benchmark_2(
        self,
        video_path: Optional[str | Path] = None,
        max_frames: int = 60,
    ) -> ScenarioKPIs:
        """
        Execute Benchmark-2: Tracking on pre-recorded .mp4 video stream (PTZ bypass).
        """
        if video_path is None or not Path(video_path).exists():
            synth_path = self.output_dir / "synthetic_test_beacon.mp4"
            video_path = self.create_synthetic_test_video(synth_path, num_frames=max_frames)

        source = VideoFileSource(video_path)
        cfg = default_config()

        preprocessor = VisionPreprocessor(cfg)
        detector = SpotDetector(cfg, preprocessor=preprocessor)
        verifier = BeaconVerifierCNN(cfg)
        optical_flow = OpticalFlowTracker(cfg.vision.optical_flow, dt=1.0 / source.fps)
        tracker = (
            KalmanTracker(cfg, dt=1.0 / source.fps)
            if cfg.tracking.tracker_type == "kalman"
            else IMMTracker(cfg, dt=1.0 / source.fps)
        )
        sm = TrackingStateMachine(cfg)

        metrics_history: list[FrameMetrics] = []

        for f in range(max_frames):
            full_frame = source.next_frame()
            if full_frame is None:
                break

            import time
            t0 = time.perf_counter()

            img = full_frame.image
            # Viewport bypass: image is processed directly
            clean_img, mask, _ = preprocessor.process(img)
            pred_x, pred_y = tracker.predict()

            candidates = detector.detect(img, mask=mask, intensity_image=clean_img)
            verified = verifier.verify_detections(img, candidates)
            best_det = tracker.select_best_detection(verified)

            hint_pt = (best_det.x, best_det.y) if best_det is not None else (pred_x, pred_y)
            flow_res = optical_flow.estimate_flow(
                curr_img=img,
                curr_pan_deg=0.0,
                curr_tilt_deg=0.0,
                hint_pos=hint_pt,
            )

            if best_det is not None:
                track = tracker.update(best_det.x, best_det.y, score=best_det.score, flow=flow_res)
                sm.step(True, full_frame.timestamp_s)
            else:
                track = tracker.coast(flow=flow_res)
                sm.step(False, full_frame.timestamp_s)

            proc_ms = (time.perf_counter() - t0) * 1000.0

            m = FrameMetrics(
                frame_index=full_frame.frame_index,
                timestamp_s=full_frame.timestamp_s,
                state=sm.state.value,
                est_x=track.x,
                est_y=track.y,
                gt_x=None,
                gt_y=None,
                error_px=0.0,  # No GT in Benchmark-2 video file
                confidence=track.confidence,
                locked=sm.is_locked,
                proc_ms=proc_ms,
                pan_deg=0.0,
                tilt_deg=0.0,
                prob_cv=track.prob_cv,
                prob_ct=track.prob_ct,
                prob_rw=track.prob_rw,
                dominant_model=track.dominant_model,
                flow_valid=track.flow_valid,
                flow_dx=track.flow_dx,
                flow_dy=track.flow_dy,
                flow_speed=track.flow_speed,
                flow_confidence=track.flow_confidence,
                flow_feature_count=track.flow_feature_count,
                flow_fb_error=track.flow_fb_error,
                flow_weight=track.flow_weight,
                flow_quality=track.flow_quality,
                flow_innovation=track.flow_innovation,
                jitter_score=track.jitter_score,
                flow_gate_reason=track.flow_gate_reason,
            )
            metrics_history.append(m)

        kpi = MetricsEvaluator.evaluate(
            scenario_name="B2_Video_Stream_Evaluation",
            history=metrics_history,
            acquisition_time_s=sm.acquisition_time_s,
            reacquisition_times=sm.reacquisition_times,
        )

        # R29 — Write per-frame x, y, confidence, state CSV for Benchmark-2
        b2_path = self.logger.write_b2_tracking_csv(metrics_history)
        print(f"  [LOG] Benchmark-2 tracking CSV saved: {b2_path}")

        return kpi

    def run_all(self, duration_s: float = 2.0) -> dict[str, list[ScenarioKPIs]]:
        """Run complete suite of Benchmark-1 and Benchmark-2."""
        b1_results = self.run_benchmark_1(duration_s=duration_s)
        b2_result = self.run_benchmark_2(max_frames=int(duration_s * 30))

        all_kpis = b1_results + [b2_result]

        # R27 — Write complete JSON KPI summary
        json_path = self.logger.write_json_summary(all_kpis)
        print(f"[LOG] KPI JSON summary saved: {json_path}")

        # Human-readable text report
        report_path = self.logger.write_text_report(all_kpis)
        print(f"[LOG] Performance report saved: {report_path}")

        # Also write legacy flat JSON for backwards compat
        MetricsEvaluator.export_json(all_kpis, str(self.output_dir / "benchmark_results_flat.json"))

        return {
            "benchmark_1": b1_results,
            "benchmark_2": [b2_result],
        }
