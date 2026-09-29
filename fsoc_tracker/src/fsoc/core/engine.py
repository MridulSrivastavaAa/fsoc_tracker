"""
src/fsoc/core/engine.py
=======================
Closed-Loop Simulation and Tracking Coordinator for FSOC Terminals.
Orchestrates:
  Source &rarr; Disturbances &rarr; Camera &rarr; Preprocessing &rarr; Detection &rarr;
  CNN Verification &rarr; Kalman Filter &rarr; State Machine &rarr; PID Controller &rarr; Camera Feedback.
"""
from __future__ import annotations
from typing import Optional
import time
import numpy as np

from .types import (
    FullFrame,
    ViewportFrame,
    FrameMetrics,
    RunSummary,
    CameraCommand,
    TrackState,
    Point,
)
from .config import AppConfig, default_config
from .camera import VirtualCamera
from ..simulation.sim_source import SimulatedSource
from ..disturbances.engine import DisturbanceEngine
from ..vision.preprocess import VisionPreprocessor
from ..vision.detector import SpotDetector
from ..vision.wide_search import WideAreaSearch
from ..vision.cnn_verifier import BeaconVerifierCNN
from ..tracking.kalman import KalmanTracker
from ..tracking.state_machine import TrackingStateMachine, State
from ..control.pid_controller import PIDController


class ClosedLoopEngine:
    """
    Master closed-loop execution engine for the FSOC tracking system.
    """
    def __init__(
        self,
        cfg: AppConfig | None = None,
        source: Optional[SimulatedSource] = None,
        disturbance_engine: Optional[DisturbanceEngine] = None,
    ) -> None:
        self.cfg = cfg or default_config()

        # 1. Physical scene & frame source
        self.source = source or SimulatedSource(self.cfg)

        # 2. Virtual pan-tilt camera
        self.camera = VirtualCamera(
            self.cfg.camera,
            scene_w=self.cfg.scene.width,
            scene_h=self.cfg.scene.height,
        )

        # 3. Environmental disturbance pipeline
        self.disturbances = disturbance_engine or DisturbanceEngine(seed=self.cfg.pipeline.seed)

        # 4. Perception pipeline
        self.preprocessor = VisionPreprocessor(self.cfg)
        self.detector = SpotDetector(self.cfg, preprocessor=self.preprocessor)
        self.wide_search = WideAreaSearch(self.cfg, camera_cfg=self.cfg.camera)
        self.verifier = BeaconVerifierCNN(self.cfg)

        # 5. Tracking & control
        self.kalman = KalmanTracker(self.cfg, dt=self.cfg.pipeline.dt)
        self.state_machine = TrackingStateMachine(self.cfg)
        self.controller = PIDController(self.cfg, camera_cfg=self.cfg.camera, dt=self.cfg.pipeline.dt)

        # 6. Advanced Turbulence & Scintillation Compensator (Phase 7)
        from ..advanced.adaptive_controller import AdaptiveTurbulenceCompensator
        self.turbulence_comp = AdaptiveTurbulenceCompensator(self.cfg, dt=self.cfg.pipeline.dt)
        self.last_turbulence_diag: dict = {}

        # Metrics log
        self.metrics_history: list[FrameMetrics] = []
        self.last_viewport: Optional[np.ndarray] = None


    def step(self) -> Optional[FrameMetrics]:
        """
        Execute one closed-loop frame cycle.
        Returns FrameMetrics, or None if frame source is exhausted.
        """
        t_start = time.perf_counter()

        # 1. Fetch source frame
        full_frame: Optional[FullFrame] = self.source.next_frame()
        if full_frame is None:
            return None


        frame_idx = full_frame.frame_index
        timestamp_s = full_frame.timestamp_s

        # 2. Render camera viewport
        vp_frame: ViewportFrame = self.camera.render(full_frame)

        # 3. Apply environmental disturbances to viewport image
        disturbed_img = self.disturbances.apply_viewport(
            vp_frame.image,
            frame_idx=frame_idx,
            timestamp_s=timestamp_s,
        )
        self.last_viewport = disturbed_img

        curr_state = self.state_machine.state
        best_det = None
        cmd = CameraCommand(0.0, 0.0)

        # 4. Processing based on current tracking state
        if curr_state == State.SEARCH:
            # Check viewport directly first
            raw_dets = self.detector.detect(disturbed_img)
            verified = self.verifier.verify_detections(disturbed_img, raw_dets)
            if verified:
                best_det = verified[0]
                self.kalman.init_track(best_det.x, best_det.y, confidence=best_det.score)
                self.state_machine.step(True, timestamp_s)
            else:
                # Wide area search on full scene if available
                # CRITICAL FIX: apply full scene disturbances first so wide search
                # doesn't cheat by using a pristine image in heavy fog/noise
                disturbed_full_scene = self.disturbances.apply_full_scene(
                    full_frame.image,
                    frame_idx=frame_idx,
                    timestamp_s=timestamp_s
                )
                res = self.wide_search.search_full_scene(disturbed_full_scene)
                if res:
                    target_pt, conf = res
                    pan, tilt, _ = self.wide_search.compute_camera_pointing(
                        target_pt,
                        scene_center_x=self.cfg.scene.width / 2.0,
                        scene_center_y=self.cfg.scene.height / 2.0,
                    )
                    # Slew camera towards target
                    d_pan = pan - self.camera.pan_deg
                    d_tilt = tilt - self.camera.tilt_deg
                    scale = self.cfg.camera.px_per_deg_x
                    cmd = CameraCommand(
                        pan_rate_deg_per_s=float(np.clip(d_pan * 3.0, -self.cfg.camera.max_pan_deg_per_s, self.cfg.camera.max_pan_deg_per_s)),
                        tilt_rate_deg_per_s=float(np.clip(d_tilt * 3.0, -self.cfg.camera.max_tilt_deg_per_s, self.cfg.camera.max_tilt_deg_per_s)),
                    )
                self.state_machine.step(False, timestamp_s)

        else:  # ACQUIRE, TRACK, LOST, REACQUIRE
            # Predict Kalman forward
            self.kalman.predict()

            # Preprocess and detect
            clean_img, mask, _ = self.preprocessor.process(disturbed_img)
            candidates = self.detector.detect(disturbed_img, mask=mask, intensity_image=clean_img)
            verified = self.verifier.verify_detections(disturbed_img, candidates)

            # Association gating
            best_det = self.kalman.select_best_detection(verified)

            if best_det is not None:
                track = self.kalman.update(best_det.x, best_det.y, score=best_det.score)
                self.state_machine.step(True, timestamp_s)
            else:
                track = self.kalman.coast()
                self.state_machine.step(False, timestamp_s)

            # Closed-loop actuator control
            if self.state_machine.is_locked:
                # Update controller with current camera slew rates for world-space FF
                self.controller.set_camera_rates(
                    pan_rate_px_s=self.camera._pan_rate * self.cfg.camera.px_per_deg_x,
                    tilt_rate_px_s=self.camera._tilt_rate * self.cfg.camera.px_per_deg_y,
                )
                cmd = self.controller.compute(track.x, track.y, track.vx, track.vy, state=self.state_machine.state.value)
            elif self.state_machine.state == State.LOST:
                # Coast control command with velocity damping
                cmd = self.controller.compute(track.x, track.y, track.vx * 0.5, track.vy * 0.5, state=self.state_machine.state.value)
            else:
                cmd = CameraCommand(0.0, 0.0)

        # 5. Adaptive Turbulence & Scintillation Compensation (Phase 7)
        beacon_peak = best_det.intensity if best_det is not None else None
        cmd, r_scale, turb_diag = self.turbulence_comp.process_frame(beacon_peak, cmd)
        self.last_turbulence_diag = turb_diag

        # Scale Kalman R based on turbulence
        if self.kalman.is_initialized and r_scale > 1.0:
            self.kalman.R0 = self.cfg.tracking.r_pos * r_scale

        # 6. Apply command to virtual camera actuator
        self.camera.apply_command(cmd, self.cfg.pipeline.dt)

        t_proc_ms = (time.perf_counter() - t_start) * 1000.0


        # 6. Compute Ground Truth comparison and metrics
        track_state = self.kalman.get_state()
        est_screen_x: Optional[float] = None
        est_screen_y: Optional[float] = None
        gt_screen_x: Optional[float] = None
        gt_screen_y: Optional[float] = None
        error_px: Optional[float] = None
        # ISRO R14 primary metric: target distance from optical boresight (320, 240)
        boresight_px: Optional[float] = None

        if self.kalman.is_initialized:
            sx, sy = self.camera.viewport_to_screen(track_state.x, track_state.y)
            est_screen_x = float(sx)
            est_screen_y = float(sy)


        if full_frame.ground_truth:
            gt_pt = full_frame.ground_truth[0]
            gt_screen_x = gt_pt.x
            gt_screen_y = gt_pt.y

            if vp_frame.ground_truth_viewport:
                gt_vp = vp_frame.ground_truth_viewport[0]

                # Centroiding accuracy: how well Kalman tracks beacon in sensor space.
                # This does NOT directly represent R14 compliance — it measures estimator quality.
                if self.kalman.is_initialized:
                    error_px = float(np.hypot(track_state.x - gt_vp.x, track_state.y - gt_vp.y))
                else:
                    error_px = float(np.hypot(self.cfg.camera.half_w - gt_vp.x,
                                              self.cfg.camera.half_h - gt_vp.y))

                # ISRO R14 boresight alignment error: distance of actual beacon
                # from the optical axis (centre of viewport = boresight).
                # R14 compliance requires this to be ≤ 10 px in steady-state tracking.
                boresight_px = float(np.hypot(
                    gt_vp.x - self.cfg.camera.half_w,
                    gt_vp.y - self.cfg.camera.half_h,
                ))

            elif est_screen_x is not None:
                error_px = float(np.hypot(est_screen_x - gt_screen_x, est_screen_y - gt_screen_y))

        metric = FrameMetrics(
            frame_index=frame_idx,
            timestamp_s=timestamp_s,
            state=self.state_machine.state.value,
            est_x=est_screen_x,
            est_y=est_screen_y,
            gt_x=gt_screen_x,
            gt_y=gt_screen_y,
            error_px=error_px,
            boresight_px=boresight_px,
            confidence=track_state.confidence,
            locked=self.state_machine.is_locked,
            proc_ms=t_proc_ms,
            pan_deg=self.camera.pan_deg,
            tilt_deg=self.camera.tilt_deg,
        )

        self.metrics_history.append(metric)
        return metric

    def run(self, max_frames: Optional[int] = None) -> RunSummary:
        """
        Run continuous closed-loop simulation until complete.
        Returns RunSummary.
        """
        frames_run = 0
        while True:
            if max_frames is not None and frames_run >= max_frames:
                break
            metric = self.step()
            if metric is None:
                break
            frames_run += 1

        return self.compute_summary()

    def compute_summary(self) -> RunSummary:
        """Compute aggregate benchmark metrics across all logged frames."""
        if not self.metrics_history:
            return RunSummary()

        n = len(self.metrics_history)
        duration_s = self.metrics_history[-1].timestamp_s - self.metrics_history[0].timestamp_s

        proc_times = [m.proc_ms for m in self.metrics_history]
        proc_mean = float(np.mean(proc_times)) if proc_times else 0.0
        proc_p95 = float(np.percentile(proc_times, 95)) if proc_times else 0.0

        fps_list = [1000.0 / max(0.1, t) for t in proc_times]
        fps_mean = float(np.mean(fps_list)) if fps_list else 0.0
        fps_min = float(np.min(fps_list)) if fps_list else 0.0

        # Errors during locked tracking
        locked_errors = [m.error_px for m in self.metrics_history if m.locked and m.error_px is not None]
        all_errors = [m.error_px for m in self.metrics_history if m.error_px is not None]

        eval_errors = locked_errors if locked_errors else all_errors
        err_mean = float(np.mean(eval_errors)) if eval_errors else 0.0
        err_max = float(np.max(eval_errors)) if eval_errors else 0.0
        err_rmse = float(np.sqrt(np.mean(np.square(eval_errors)))) if eval_errors else 0.0

        return RunSummary(
            duration_s=float(duration_s),
            fps_mean=fps_mean,
            fps_min=fps_min,
            acquisition_time_s=self.state_machine.acquisition_time_s,
            reacquisition_times_s=list(self.state_machine.reacquisition_times),
            error_mean_px=err_mean,
            error_max_px=err_max,
            error_rmse_px=err_rmse,
            lock_retention_pct=self.state_machine.lock_retention_pct,
            target_loss_pct=self.state_machine.target_loss_pct,
            proc_ms_mean=proc_mean,
            proc_ms_p95=proc_p95,
        )

    def reset(self) -> None:
        """Reset engine and all submodules for a fresh run."""
        self.source.reset()
        self.camera = VirtualCamera(
            self.cfg.camera,
            scene_w=self.cfg.scene.width,
            scene_h=self.cfg.scene.height,
        )
        self.disturbances.reset()
        self.kalman.reset()
        self.state_machine.reset()
        self.controller.reset()
        self.turbulence_comp.reset()
        self.metrics_history.clear()
        self.last_viewport = None

