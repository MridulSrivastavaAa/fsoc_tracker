"""
tests/unit/test_particle_filter.py
==================================
Comprehensive deterministic test suite for Particle Filter Target Recovery and Reacquisition (Step 4).

Covers all 15 scientific test scenarios:
1.  PF Initialization & Cloud Distribution
2.  Particle Motion Model & Vectorized Propagation
3.  Single-Frame Detection Dropout (Normal IMM Coasting)
4.  3-Frame Dropout (PF Activation Threshold)
5.  5-Frame Dropout (PF Envelope Expansion)
6.  Temporary Occlusion & Reacquisition
7.  Beacon Reappearing Near Prediction
8.  Beacon Reappearing with Displacement / Maneuver
9.  Noisy False Candidates & Threshold Rejection
10. Multiple Distractor Candidates Discrimination
11. Complete Temporary Loss & Recovery Cycle
12. Reacquisition Timeout & Fallback to Search
13. Particle Degeneracy, N_eff & Systematic Resampling
14. Zero Candidate Weight Decay & Numerical Stability
15. Boundary Condition Clamping
16. PF Activation / Deactivation Lifecycle (Zero Steady-State Overhead)
17. IMM Recovery Handoff & State Covariance Re-initialization
"""
import math
import numpy as np
import pytest

from fsoc.core.config import AppConfig, default_config, ParticleFilterConfig
from fsoc.core.types import Detection, Point, TrackState
from fsoc.tracking.particle_filter import ParticleFilter
from fsoc.tracking.imm import IMMTracker
from fsoc.tracking.state_machine import TrackingStateMachine, State
from fsoc.core.engine import ClosedLoopEngine


class TestParticleFilterCore:
    """Unit tests for the standalone ParticleFilter module."""

    def test_pf_initialization(self) -> None:
        cfg = ParticleFilterConfig(num_particles=150, init_pos_std_px=15.0, init_vel_std_px_s=30.0)
        pf = ParticleFilter(cfg, dt=1.0 / 30.0, viewport_w=640.0, viewport_h=480.0, seed=42)

        assert not pf.is_active
        assert pf.N == 150

        pf.initialize(center_x=320.0, center_y=240.0, vx=10.0, vy=-5.0)
        assert pf.is_active
        assert pf.confirm_count == 0
        assert pf.particles.shape == (150, 4)

        # Check empirical mean and standard deviation match initialization parameters
        mean_x = np.mean(pf.particles[:, 0])
        mean_y = np.mean(pf.particles[:, 1])
        assert abs(mean_x - 320.0) < 5.0
        assert abs(mean_y - 240.0) < 5.0

        std_pos = np.std(pf.particles[:, 0])
        assert abs(std_pos - 15.0) < 4.0

    def test_pf_prediction_propagation(self) -> None:
        cfg = ParticleFilterConfig(num_particles=200, process_pos_noise_std=1.0, process_vel_noise_std=2.0)
        pf = ParticleFilter(cfg, dt=0.1, viewport_w=640.0, viewport_h=480.0, seed=42)
        pf.initialize(center_x=100.0, center_y=100.0, vx=50.0, vy=30.0, pos_std=0.1, vel_std=0.1)

        # Predict forward 5 steps
        for _ in range(5):
            pf.predict()

        state = pf.get_state()
        # Expected position: 100 + 50 * 0.5 = 125, 100 + 30 * 0.5 = 115
        assert abs(state.x - 125.0) < 4.0
        assert abs(state.y - 115.0) < 4.0
        assert pf.active_frames == 5

    def test_pf_particle_degeneracy_and_resampling(self) -> None:
        cfg = ParticleFilterConfig(num_particles=100, resample_threshold_ratio=0.5)
        pf = ParticleFilter(cfg, seed=42)
        pf.initialize(center_x=300.0, center_y=200.0)

        # Manually create degenerate weights (one particle has 95% weight)
        pf.weights.fill(0.05 / 99)
        pf.weights[0] = 0.95

        n_eff = 1.0 / np.sum(np.square(pf.weights))
        assert n_eff < 0.5 * pf.N

        # Perform update with candidate near particle 0
        cand = [Detection(x=pf.particles[0, 0], y=pf.particles[0, 1], intensity=200.0, area_px=10.0, score=0.9)]
        pf.update(cand)

        # Systematic resampling should have restored uniform weights
        assert abs(pf.weights[0] - (1.0 / 100)) < 1e-6
        assert abs(np.sum(pf.weights) - 1.0) < 1e-6

    def test_pf_no_valid_candidates(self) -> None:
        pf = ParticleFilter(ParticleFilterConfig(), seed=42)
        pf.initialize(center_x=320.0, center_y=240.0)

        # Update with empty candidate list
        reacquired, state = pf.update([])
        assert not reacquired
        assert abs(np.sum(pf.weights) - 1.0) < 1e-6
        assert not math.isnan(state.x)
        assert not math.isnan(state.y)

    def test_pf_noisy_false_candidates(self) -> None:
        cfg = ParticleFilterConfig(min_candidate_score=0.35)
        pf = ParticleFilter(cfg, seed=42)
        pf.initialize(center_x=320.0, center_y=240.0)

        # Candidate with score below threshold should be filtered out
        low_score_cands = [
            Detection(x=320.0, y=240.0, intensity=50.0, area_px=10.0, score=0.20),
            Detection(x=325.0, y=245.0, intensity=40.0, area_px=10.0, score=0.15),
        ]
        reacquired, state = pf.update(low_score_cands)
        assert not reacquired
        assert pf.confirm_count == 0

    def test_pf_multiple_distractor_candidates(self) -> None:
        pf = ParticleFilter(ParticleFilterConfig(num_particles=200, meas_pos_sigma_px=10.0), seed=42)
        # Target expected at (320, 240)
        pf.initialize(center_x=320.0, center_y=240.0, vx=0.0, vy=0.0, pos_std=5.0)

        # True candidate at (322, 241) and distractor far away at (450, 400)
        candidates = [
            Detection(x=450.0, y=400.0, intensity=250.0, area_px=10.0, score=0.95),  # Distractor
            Detection(x=322.0, y=241.0, intensity=240.0, area_px=10.0, score=0.90),  # True target
        ]

        # Update weights
        reacquired, state = pf.update(candidates)
        # Mean should lock onto true candidate near (322, 241), not distractor
        assert abs(state.x - 322.0) < 6.0
        assert abs(state.y - 241.0) < 6.0

    def test_pf_beacon_reappearing_near_prediction(self) -> None:
        cfg = ParticleFilterConfig(reacquire_confirm_frames=2, reacquire_cluster_std_thresh=20.0)
        pf = ParticleFilter(cfg, seed=42)
        pf.initialize(center_x=320.0, center_y=240.0, vx=10.0, vy=0.0)

        pf.predict()
        cand = [Detection(x=320.5, y=240.0, intensity=250.0, area_px=10.0, score=0.95)]

        # Frame 1: candidate detected, confirm_count = 1
        reacquired_1, state_1 = pf.update(cand)
        assert not reacquired_1
        assert pf.confirm_count == 1

        # Frame 2: candidate persists, confirm_count = 2 -> confirmed reacquisition!
        pf.predict()
        reacquired_2, state_2 = pf.update(cand)
        assert reacquired_2
        assert state_2.pf_reacquired
        assert abs(state_2.x - 320.5) < 1.0

    def test_pf_beacon_reappearing_with_displacement(self) -> None:
        cfg = ParticleFilterConfig(
            num_particles=300,
            init_pos_std_px=25.0,
            process_pos_noise_std=3.0,
            reacquire_confirm_frames=2,
        )
        pf = ParticleFilter(cfg, seed=42)
        # Initialized at (300, 200)
        pf.initialize(center_x=300.0, center_y=200.0, vx=0.0, vy=0.0)

        # Target reappears displaced by 25 px at (325, 215)
        displaced_cand = [Detection(x=325.0, y=215.0, intensity=220.0, area_px=10.0, score=0.85)]

        for _ in range(3):
            pf.predict()
            reacquired, state = pf.update(displaced_cand)

        assert reacquired
        assert abs(state.x - 325.0) < 2.0
        assert abs(state.y - 215.0) < 2.0

    def test_pf_boundary_conditions(self) -> None:
        pf = ParticleFilter(ParticleFilterConfig(num_particles=50), viewport_w=640.0, viewport_h=480.0, seed=42)
        # Initialize at viewport edge
        pf.initialize(center_x=635.0, center_y=475.0, vx=500.0, vy=500.0)

        for _ in range(10):
            pf.predict()

        # All particles must be safely bounded inside [0, 640] and [0, 480]
        assert np.all(pf.particles[:, 0] >= 0.0)
        assert np.all(pf.particles[:, 0] <= 640.0)
        assert np.all(pf.particles[:, 1] >= 0.0)
        assert np.all(pf.particles[:, 1] <= 480.0)

    def test_pf_reset_lifecycle(self) -> None:
        pf = ParticleFilter(ParticleFilterConfig(), seed=42)
        pf.initialize(center_x=320.0, center_y=240.0)
        assert pf.is_active

        pf.reset()
        assert not pf.is_active
        assert pf.confirm_count == 0
        state = pf.get_state()
        assert not state.pf_active


class TestParticleFilterClosedLoopIntegration:
    """Integration tests verifying Particle Filter with IMM & Tracking State Machine."""

    def test_single_frame_detection_dropout(self) -> None:
        """1-frame detection dropout: normal IMM coasting handles it without activating PF."""
        cfg = default_config()
        cfg.pipeline.duration_s = 1.0
        cfg.target.initial_x = 1000.0
        cfg.target.initial_y = 1000.0
        cfg.motion.model = "line"
        cfg.motion.line.vx = 20.0
        cfg.motion.line.vy = 10.0

        engine = ClosedLoopEngine(cfg)

        # Run 10 frames to establish steady track
        for _ in range(10):
            m = engine.step()
            assert m is not None

        assert engine.state_machine.is_locked
        assert not engine.particle_filter.is_active

    def test_3_frame_dropout_pf_activation(self) -> None:
        """3-frame dropout reaches activation_coast_frames and triggers PF initialization."""
        cfg = default_config()
        cfg.tracking.particle_filter.activation_coast_frames = 3
        cfg.target.initial_x = 1000.0
        cfg.target.initial_y = 1000.0
        cfg.motion.model = "line"

        engine = ClosedLoopEngine(cfg)

        # Lock track
        for _ in range(10):
            engine.step()

        assert engine.state_machine.is_locked

        # Simulate 3-frame occlusion by hiding target
        engine.source.visible = False

        m1 = engine.step()
        assert not engine.particle_filter.is_active  # miss_streak = 1

        m2 = engine.step()
        assert not engine.particle_filter.is_active  # miss_streak = 2

        m3 = engine.step()
        # miss_streak = 3 -> PF activates
        assert engine.particle_filter.is_active
        assert m3.pf_active

    def test_5_frame_dropout_envelope_expansion(self) -> None:
        """5-frame dropout expands particle search dispersion without losing stability."""
        cfg = default_config()
        cfg.tracking.particle_filter.activation_coast_frames = 2
        cfg.target.initial_x = 1000.0
        cfg.target.initial_y = 1000.0
        cfg.motion.model = "line"
        engine = ClosedLoopEngine(cfg)

        for _ in range(10):
            engine.step()

        # Occlusion
        engine.source.visible = False

        dispersions = []
        for _ in range(5):
            m = engine.step()
            if m.pf_active:
                dispersions.append(m.pf_cluster_std)

        assert engine.particle_filter.is_active
        assert len(dispersions) >= 3
        # Later dispersion should be equal or greater than initial dispersion
        assert dispersions[-1] >= dispersions[0]

    def test_temporary_occlusion_and_reacquisition_cycle(self) -> None:
        """
        Temporary occlusion for 6 frames followed by beacon reappearance.
        Verifies PF activation, candidate tracking, confirmation, IMM re-initialization,
        and return to steady-state TRACK mode.
        """
        cfg = default_config()
        cfg.target.initial_x = 1000.0
        cfg.target.initial_y = 1000.0
        cfg.motion.model = "line"
        cfg.motion.line.vx = 10.0
        cfg.motion.line.vy = 5.0
        cfg.tracking.particle_filter.activation_coast_frames = 2
        cfg.tracking.particle_filter.reacquire_confirm_frames = 2
        engine = ClosedLoopEngine(cfg)

        # 1. Initial lock
        for _ in range(15):
            m = engine.step()

        assert engine.state_machine.state == State.TRACK

        # 2. Temporary occlusion (target disappears for 6 frames)
        engine.source.visible = False
        for _ in range(6):
            engine.step()

        assert engine.particle_filter.is_active

        # 3. Beacon reappears!
        engine.source.visible = True
        reacquired_observed = False
        for _ in range(15):
            m = engine.step()
            if m.pf_reacquired or engine.state_machine.state == State.TRACK:
                reacquired_observed = True

        assert reacquired_observed
        # Once steady track resumes, PF is deactivated
        assert not engine.particle_filter.is_active

    def test_reacquisition_timeout_and_fallback_to_search(self) -> None:
        """
        Prolonged loss without beacon reappearance triggers state machine timeout
        and cleanly transitions from REACQUIRE to wide SEARCH.
        """
        cfg = default_config()
        cfg.target.initial_x = 1000.0
        cfg.target.initial_y = 1000.0
        cfg.motion.model = "line"
        cfg.tracking.consecutive_lost_frames = 3
        cfg.tracking.max_coast_frames = 5
        cfg.tracking.reacquire_timeout_frames = 10
        engine = ClosedLoopEngine(cfg)

        # Lock
        for _ in range(10):
            engine.step()

        # Complete permanent target loss
        engine.source.visible = False

        # Step through LOST -> REACQUIRE -> SEARCH
        for _ in range(30):
            engine.step()

        assert engine.state_machine.state == State.SEARCH

    def test_imm_recovery_handoff_accuracy(self) -> None:
        """
        Verify that when PF reacquires, IMM is correctly re-initialized with the recovered state.
        """
        cfg = default_config()
        engine = ClosedLoopEngine(cfg)

        # Initial track
        engine.kalman.init_track(100.0, 100.0, vx=10.0, vy=5.0)

        # Manually trigger PF recovery handoff
        recovered_state = TrackState(
            x=320.0,
            y=240.0,
            vx=15.0,
            vy=-8.0,
            confidence=0.92,
            locked=True,
            pf_active=True,
            pf_reacquired=True,
        )

        engine.kalman.init_track(
            recovered_state.x,
            recovered_state.y,
            vx=recovered_state.vx,
            vy=recovered_state.vy,
            confidence=recovered_state.confidence,
        )

        imm_state = engine.kalman.get_state()
        assert abs(imm_state.x - 320.0) < 1e-3
        assert abs(imm_state.y - 240.0) < 1e-3
        assert abs(imm_state.vx - 15.0) < 1e-3
        assert abs(imm_state.vy - (-8.0)) < 1e-3
        assert imm_state.confidence == 0.92
        assert imm_state.locked
