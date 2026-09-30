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
from ..vision.optical_flow import OpticalFlowTracker
from ..tracking.kalman import KalmanTracker
from ..tracking.imm import IMMTracker
from ..tracking.particle_filter import ParticleFilter
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
        self.optical_flow = OpticalFlowTracker(self.cfg.vision.optical_flow, dt=self.cfg.pipeline.dt)

        # 5. Tracking & control (IMM multi-model estimator or single Kalman baseline)
        if self.cfg.tracking.tracker_type == "kalman":
            self.kalman = KalmanTracker(self.cfg, dt=self.cfg.pipeline.dt)
        else:
            self.kalman = IMMTracker(self.cfg, dt=self.cfg.pipeline.dt)

        # 5b. Particle Filter recovery mechanism (Step 4)
        self.particle_filter = ParticleFilter(
            self.cfg,
            dt=self.cfg.pipeline.dt,
            viewport_w=self.cfg.camera.viewport_w,
            viewport_h=self.cfg.camera.viewport_h,
            seed=self.cfg.pipeline.seed,
        )

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
        reacquired_this_frame = False

        # 4. Processing based on current tracking state
        if curr_state == State.SEARCH:
            # Check viewport directly first
            raw_dets = self.detector.detect(disturbed_img)
            verified = self.verifier.verify_detections(disturbed_img, raw_dets)
            if verified:
                best_det = verified[0]
                self.kalman.init_track(best_det.x, best_det.y, confidence=best_det.score)
                self.particle_filter.reset()
                self.optical_flow.reset()
                self.optical_flow.estimate_flow(
                    curr_img=disturbed_img,
                    curr_pan_deg=self.camera.pan_deg,
                    curr_tilt_deg=self.camera.tilt_deg,
                    hint_pos=(best_det.x, best_det.y),
                    px_per_deg_x=self.cfg.camera.px_per_deg_x,
                    px_per_deg_y=self.cfg.camera.px_per_deg_y,
                )
                self.state_machine.step(True, timestamp_s)
            else:
                # Wide area search on full scene if available
                # CRITICAL FIX: apply full scene disturbances first so wide search
                # doesn't cheat by using a pristine image in heavy fog/noise
                disturbed_full_scene = self.disturbances.apply_full_scene(
                    full_frame.image,
                    dt=self.cfg.pipeline.dt
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
                    cmd = CameraCommand(
                        pan_rate_deg_per_s=float(np.clip(d_pan * 3.0, -self.cfg.camera.max_pan_deg_per_s, self.cfg.camera.max_pan_deg_per_s)),
                        tilt_rate_deg_per_s=float(np.clip(d_tilt * 3.0, -self.cfg.camera.max_tilt_deg_per_s, self.cfg.camera.max_tilt_deg_per_s)),
                    )
                self.state_machine.step(False, timestamp_s)

        else:  # ACQUIRE, TRACK, LOST, REACQUIRE
            # Predict Kalman forward
            pred_x, pred_y = self.kalman.predict()

            # Preprocess and detect
            clean_img, mask, _ = self.preprocessor.process(disturbed_img)
            candidates = self.detector.detect(disturbed_img, mask=mask, intensity_image=clean_img)
            verified = self.verifier.verify_detections(disturbed_img, candidates)

            # Association gating
            best_det = self.kalman.select_best_detection(verified)

            # Local sparse optical flow estimation
            hint_pt = (best_det.x, best_det.y) if best_det is not None else (pred_x, pred_y)
            flow_res = self.optical_flow.estimate_flow(
                curr_img=disturbed_img,
                curr_pan_deg=self.camera.pan_deg,
                curr_tilt_deg=self.camera.tilt_deg,
                hint_pos=hint_pt,
                px_per_deg_x=self.cfg.camera.px_per_deg_x,
                px_per_deg_y=self.cfg.camera.px_per_deg_y,
            )

            # Step 4: Particle Filter Reacquisition / Recovery Pipeline
            pf_cfg = self.cfg.tracking.particle_filter
            if pf_cfg.enabled and self.particle_filter.is_active:
                # 1. Propagate particles forward
                self.particle_filter.predict()
                # 2. Update weights using all candidate spots / verified detections in viewport
                pf_candidates = verified if verified else candidates
                reacquired, pf_state = self.particle_filter.update(pf_candidates)
                if reacquired:
                    reacquired_this_frame = True
                    # Confirmed recovery: hand off recovered state to IMM
                    self.kalman.init_track(
                        pf_state.x,
                        pf_state.y,
                        vx=pf_state.vx,
                        vy=pf_state.vy,
                        confidence=pf_state.confidence,
                    )
                    self.particle_filter.reset()
                    self.state_machine.transition_to(State.TRACK, timestamp_s)
                    track = self.kalman.get_state()

            if not reacquired_this_frame:
                if best_det is not None:
                    track = self.kalman.update(best_det.x, best_det.y, score=best_det.score, flow=flow_res)
                    self.state_machine.step(True, timestamp_s)
                    # If normal confident tracking resumed, ensure PF is reset/inactive
                    if self.particle_filter.is_active and track.confidence >= pf_cfg.activation_confidence_thresh:
                        self.particle_filter.reset()
                else:
                    track = self.kalman.coast(flow=flow_res)
                    self.state_machine.step(False, timestamp_s)

                    # Trigger Particle Filter activation on signal loss / drop / high uncertainty
                    if pf_cfg.enabled:
                        should_activate_pf = (
                            self.state_machine.state in (State.LOST, State.REACQUIRE) or
                            self.state_machine.miss_streak >= pf_cfg.activation_coast_frames or
                            track.confidence < pf_cfg.activation_confidence_thresh or
                            track.uncertainty > pf_cfg.activation_uncertainty_px
                        )
                        if should_activate_pf and not self.particle_filter.is_active:
                            self.particle_filter.initialize(
                                center_x=track.x,
                                center_y=track.y,
                                vx=track.vx,
                                vy=track.vy,
                                pos_std=pf_cfg.init_pos_std_px,
                                vel_std=pf_cfg.init_vel_std_px_s,
                            )

            # Closed-loop actuator control
            if self.state_machine.is_locked:
                # Update controller with current camera slew rates for world-space FF
                self.controller.set_camera_rates(
                    pan_rate_px_s=self.camera._pan_rate * self.cfg.camera.px_per_deg_x,
                    tilt_rate_px_s=self.camera._tilt_rate * self.cfg.camera.px_per_deg_y,
                )
                cmd = self.controller.compute(track.x, track.y, track.vx, track.vy, state=self.state_machine.state.value)
            elif self.particle_filter.is_active:
                pf_st = self.particle_filter.get_state()
                cmd = self.controller.compute(pf_st.x, pf_st.y, pf_st.vx * 0.5, pf_st.vy * 0.5, state=self.state_machine.state.value)
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

        # 7. Compute Ground Truth comparison and metrics
        track_state = self.kalman.get_state()
        pf_info = self.particle_filter.get_state()
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
                if self.kalman.is_initialized:
                    error_px = float(np.hypot(track_state.x - gt_vp.x, track_state.y - gt_vp.y))
                else:
                    error_px = float(np.hypot(self.cfg.camera.half_w - gt_vp.x,
                                              self.cfg.camera.half_h - gt_vp.y))

                # ISRO R14 boresight alignment error: distance of actual beacon
                # from the optical axis (centre of viewport = boresight).
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
            prob_cv=track_state.prob_cv,
            prob_ct=track_state.prob_ct,
            prob_rw=track_state.prob_rw,
            dominant_model=track_state.dominant_model,
            flow_valid=track_state.flow_valid,
            flow_dx=track_state.flow_dx,
            flow_dy=track_state.flow_dy,
            flow_speed=track_state.flow_speed,
            flow_confidence=track_state.flow_confidence,
            flow_feature_count=track_state.flow_feature_count,
            flow_fb_error=track_state.flow_fb_error,
            flow_weight=track_state.flow_weight,
            flow_quality=track_state.flow_quality,
            flow_innovation=track_state.flow_innovation,
            jitter_score=track_state.jitter_score,
            flow_gate_reason=track_state.flow_gate_reason,
            pf_active=pf_info.pf_active,
            pf_particles=pf_info.pf_particles,
            pf_cluster_std=pf_info.pf_cluster_std,
            pf_n_eff=pf_info.pf_n_eff,
            pf_reacquired=reacquired_this_frame,
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

        # Reacquisition and target loss metrics
        reacq_times = list(self.state_machine.reacquisition_times)
        lost_count = sum(1 for t, f, to in self.state_machine.transitions if to == State.LOST.value)
        reacq_count = len(reacq_times)

        if lost_count > 0:
            reacq_success_pct = float(min(100.0, 100.0 * reacq_count / lost_count))
        elif reacq_count > 0:
            reacq_success_pct = 100.0
        else:
            reacq_success_pct = 100.0 if self.state_machine.target_loss_pct == 0.0 else 0.0

        reacq_mean = float(np.mean(reacq_times)) if reacq_times else None
        reacq_p95 = float(np.percentile(reacq_times, 95)) if reacq_times else None
        reacq_max = float(np.max(reacq_times)) if reacq_times else None

        # False reacquisition count: check frames where reacquisition occurred with large error > 30 px
        reacq_frame_indices = [
            i for i, m in enumerate(self.metrics_history)
            if m.pf_reacquired or (i > 0 and self.metrics_history[i-1].state in ("LOST", "REACQUIRE") and m.state in ("TRACK", "ACQUIRE"))
        ]
        false_reacq_count = sum(
            1 for idx in reacq_frame_indices
            if self.metrics_history[idx].error_px is not None and self.metrics_history[idx].error_px > 30.0
        )

        return RunSummary(
            duration_s=float(duration_s),
            fps_mean=fps_mean,
            fps_min=fps_min,
            acquisition_time_s=self.state_machine.acquisition_time_s,
            reacquisition_times_s=reacq_times,
            reacquisition_success_pct=reacq_success_pct,
            reacquisition_time_mean_s=reacq_mean,
            reacquisition_time_p95_s=reacq_p95,
            reacquisition_time_max_s=reacq_max,
            false_reacquisition_count=false_reacq_count,
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
        self.particle_filter.reset()
        self.optical_flow.reset()
        self.state_machine.reset()
        self.controller.reset()
        self.turbulence_comp.reset()
        self.metrics_history.clear()
        self.last_viewport = None


