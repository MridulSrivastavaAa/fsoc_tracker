"""
tests/unit/test_tracking_control.py
====================================
Comprehensive Unit & Closed-Loop Integration Tests for Phase 4:
1. Kalman Filter Trajectory Estimation & Coasting
2. 5-State Autonomous Tracking Machine
3. Feed-Forward PID Actuator Controller
4. Full Closed-Loop Simulation Engine
"""
import time
import pytest
import numpy as np

from fsoc.core.types import Detection, TrackState, CameraCommand, FrameMetrics, RunSummary
from fsoc.core.config import (
    AppConfig,
    TrackingConfig,
    ControlConfig,
    default_config,
)
from fsoc.tracking.kalman import KalmanTracker
from fsoc.tracking.state_machine import TrackingStateMachine, State
from fsoc.control.pid_controller import PIDController
from fsoc.core.engine import ClosedLoopEngine


# ===========================================================================
# 1. Kalman Tracker Tests
# ===========================================================================

class TestKalmanTracker:
    def test_init_track(self) -> None:
        tracker = KalmanTracker()
        tracker.init_track(100.0, 150.0, vx=10.0, vy=-5.0, confidence=0.9)
        state = tracker.get_state()

        assert state.x == 100.0
        assert state.y == 150.0
        assert state.vx == 10.0
        assert state.vy == -5.0
        assert state.confidence == 0.9
        assert state.locked is True

    def test_constant_velocity_tracking(self) -> None:
        """Verify Kalman tracker converges to true velocity and tracks smoothly."""
        dt = 1.0 / 30.0
        tracker = KalmanTracker(dt=dt)

        true_x, true_y = 50.0, 80.0
        vx, vy = 90.0, -45.0  # px/s

        tracker.init_track(true_x, true_y, vx=0.0, vy=0.0)

        rng = np.random.RandomState(42)
        for _ in range(30):
            true_x += vx * dt
            true_y += vy * dt
            # Add measurement noise (sigma = 1.5 px)
            meas_x = true_x + rng.randn() * 1.5
            meas_y = true_y + rng.randn() * 1.5

            tracker.predict()
            tracker.update(meas_x, meas_y, score=0.95)

        state = tracker.get_state()
        pos_err = np.hypot(state.x - true_x, state.y - true_y)
        # Position error should be well under 2.0 px (meas noise sigma=1.5 px)
        assert pos_err < 2.0
        # Estimated velocity should be close to true velocity
        assert abs(state.vx - vx) < 15.0
        assert abs(state.vy - vy) < 15.0

    def test_association_gate(self) -> None:
        tracker = KalmanTracker()
        tracker.init_track(200.0, 200.0)

        # Within gate (distance 20 px < 60 px)
        assert tracker.is_within_gate(210.0, 210.0) is True
        # Outside gate (distance 100 px > 60 px)
        assert tracker.is_within_gate(300.0, 200.0) is False

    def test_candidate_selection_within_gate(self) -> None:
        tracker = KalmanTracker()
        tracker.init_track(200.0, 200.0)

        dets = [
            Detection(x=500.0, y=500.0, intensity=250.0, area_px=20.0, score=0.99), # distant false alarm
            Detection(x=205.0, y=202.0, intensity=200.0, area_px=15.0, score=0.85), # true target near gate
        ]
        best = tracker.select_best_detection(dets)
        assert best is not None
        assert best.x == 205.0

    def test_coasting_during_occlusion(self) -> None:
        """Verify tracker coasts with estimated velocity during temporary signal loss."""
        dt = 1.0 / 30.0
        tracker = KalmanTracker(dt=dt)
        tracker.init_track(100.0, 100.0, vx=60.0, vy=0.0)

        # Coast for 5 frames
        for _ in range(5):
            tracker.predict()
            state = tracker.coast()

        # Expected position: 100 + 60 * (5 * 1/30) = 110 px
        assert abs(state.x - 110.0) < 0.5
        assert state.locked is True  # Coasting within max_coast_frames maintains lock
        assert state.confidence < 0.8  # Confidence decays during occlusion


# ===========================================================================
# 2. State Machine Tests
# ===========================================================================

class TestTrackingStateMachine:
    def test_transition_sequence(self) -> None:
        sm = TrackingStateMachine()
        assert sm.state == State.SEARCH

        # 1. Detection found -> transitions to ACQUIRE
        sm.step(detection_found=True, timestamp_s=0.033)
        assert sm.state == State.ACQUIRE

        # 2. Need 3 consecutive detections to enter TRACK
        sm.step(detection_found=True, timestamp_s=0.066)
        assert sm.state == State.ACQUIRE
        sm.step(detection_found=True, timestamp_s=0.100)
        assert sm.state == State.TRACK
        assert sm.is_locked is True

        # 3. 10 consecutive misses to enter LOST
        for i in range(9):
            sm.step(detection_found=False, timestamp_s=0.133 + i * 0.033)
            assert sm.state == State.TRACK
        sm.step(detection_found=False, timestamp_s=0.450)
        assert sm.state == State.LOST
        assert sm.is_locked is False

    def test_recovery_from_lost_to_track(self) -> None:
        sm = TrackingStateMachine()
        # Acquire and lock
        for i in range(4):
            sm.step(detection_found=True, timestamp_s=i * 0.033)
        assert sm.state == State.TRACK

        # Trigger LOST
        for i in range(10):
            sm.step(detection_found=False, timestamp_s=(4 + i) * 0.033)
        assert sm.state == State.LOST

        # Immediate re-detection recovers directly to TRACK
        sm.step(detection_found=True, timestamp_s=0.500)
        assert sm.state == State.TRACK
        assert len(sm.reacquisition_times) == 1


# ===========================================================================
# 3. PID Controller Tests
# ===========================================================================

class TestPIDController:
    def test_zero_error_produces_zero_command(self) -> None:
        ctrl = PIDController()
        # Viewport center is at (320, 240)
        cmd = ctrl.compute(320.0, 240.0, vel_x=0.0, vel_y=0.0)
        assert abs(cmd.pan_rate_deg_per_s) < 1e-4
        assert abs(cmd.tilt_rate_deg_per_s) < 1e-4

    def test_proportional_direction(self) -> None:
        ctrl = PIDController()
        # Target at x=400 (to the right of 320) -> should command positive pan rate
        cmd = ctrl.compute(400.0, 240.0)
        assert cmd.pan_rate_deg_per_s > 0.0

        # Target at y=180 (above 240) -> should command negative tilt rate
        cmd2 = ctrl.compute(320.0, 180.0)
        assert cmd2.tilt_rate_deg_per_s < 0.0

    def test_actuator_speed_clamping(self) -> None:
        ctrl = PIDController()
        # Huge error (x=2000) -> must clamp to max_pan_deg_per_s (5.0 deg/s)
        cmd = ctrl.compute(2000.0, 240.0)
        assert cmd.pan_rate_deg_per_s == pytest.approx(5.0)

    def test_feedforward_velocity_boost(self) -> None:
        ctrl = PIDController()
        # Compare command without velocity vs with positive velocity
        cmd_no_ff = ctrl.compute(330.0, 240.0, vel_x=0.0)
        ctrl.reset()
        cmd_with_ff = ctrl.compute(330.0, 240.0, vel_x=100.0)

        assert cmd_with_ff.pan_rate_deg_per_s > cmd_no_ff.pan_rate_deg_per_s


# ===========================================================================
# 4. Full Closed-Loop Simulation Engine Tests
# ===========================================================================

class TestClosedLoopEngine:
    def test_engine_single_step(self) -> None:
        cfg = default_config()
        cfg.pipeline.duration_s = 2.0
        engine = ClosedLoopEngine(cfg)

        metric = engine.step()
        assert metric is not None
        assert metric.frame_index == 0
        assert metric.proc_ms > 0.0
        assert metric.state in [s.value for s in State]

    def test_engine_closed_loop_tracking_lock(self) -> None:
        """
        Verify complete closed-loop run establishes lock and achieves
        coarse tracking error <= 10 pixels (ISRO PS requirement R14).
        """
        cfg = default_config()
        # Configure target with line motion near initial camera view
        cfg.pipeline.duration_s = 2.0  # 60 frames
        cfg.target.initial_x = 1000.0
        cfg.target.initial_y = 1000.0
        cfg.target.brightness = 230
        cfg.motion.model = "line"
        cfg.motion.line.vx = 40.0
        cfg.motion.line.vy = 20.0

        engine = ClosedLoopEngine(cfg)
        summary = engine.run(max_frames=60)

        assert summary.duration_s > 0.0
        assert len(engine.metrics_history) == 60

        # Check tracking error on locked frames
        locked_errors = [m.error_px for m in engine.metrics_history if m.locked and m.error_px is not None]
        assert len(locked_errors) > 20  # Must establish lock

        mean_locked_err = float(np.mean(locked_errors))
        # Must meet requirement R14: error <= 10.0 pixels
        assert mean_locked_err <= 10.0

        # Processing time must be real-time (< 33 ms per frame)
        assert summary.proc_ms_mean < 33.0
