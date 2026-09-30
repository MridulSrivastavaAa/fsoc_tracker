"""
tests/unit/test_imm.py
======================
Comprehensive Unit Tests for the IMM (Interacting Multiple Model) State Estimator.

Test Coverage:
1. CV Model (Constant Velocity kinematic filter)
2. CT Model (Coordinated Turn Rate EKF filter)
3. RW Model (Random Walk high-maneuver filter)
4. Model Mixing (Interaction probabilities and mixed initial conditions)
5. Probability Update (Bayesian likelihood and Markov prior updates)
6. State Combination (Weighted state output & covariance spread-of-means)
7. Innovation Gating (Association gate and outlier rejection)
8. Missing Measurements (Coasting through occlusions without tracker reset)
9. Small/Zero Turn Rate (Numerical stability for omega -> 0)
10. Long-Horizon Numerical Stability (Covariance conditioning over 1,000 steps)
"""
import math
import pytest
import numpy as np

from fsoc.core.types import Detection, TrackState
from fsoc.core.config import TrackingConfig, AppConfig, default_config
from fsoc.tracking.models import CVSubFilter, CTSubFilter, RWSubFilter
from fsoc.tracking.imm import IMMTracker


# ===========================================================================
# 1. CV Model Tests
# ===========================================================================

class TestCVSubFilter:
    def test_cv_prediction_linear_motion(self) -> None:
        """Verify CV filter predicts linear motion x(t+dt) = x(t) + vx*dt."""
        dt = 0.1
        cv = CVSubFilter(dt=dt, q_pos=0.01, q_vel=0.01)
        x_init = np.array([100.0, 200.0, 50.0, -30.0], dtype=np.float64)
        P_init = np.eye(4, dtype=np.float64) * 10.0
        cv.set_state(x_init, P_init)

        x_pred, P_pred = cv.predict()
        assert x_pred[0] == pytest.approx(105.0)  # 100 + 50*0.1
        assert x_pred[1] == pytest.approx(197.0)  # 200 - 30*0.1
        assert x_pred[2] == pytest.approx(50.0)
        assert x_pred[3] == pytest.approx(-30.0)
        # Covariance grew due to Q
        assert P_pred[0, 0] > P_init[0, 0]

    def test_cv_likelihood_and_update(self) -> None:
        dt = 0.0333
        cv = CVSubFilter(dt=dt)
        cv.set_state(np.array([100.0, 100.0, 0.0, 0.0]), np.eye(4) * 4.0)
        z = np.array([102.0, 101.0])
        R = np.eye(2) * 4.0

        lik, y, S, nis = cv.compute_likelihood(z, R)
        assert lik > 0.0
        assert np.allclose(y, [2.0, 1.0])
        assert nis > 0.0

        x_up, P_up = cv.update(z, R)
        # Position should move towards measurement
        assert x_up[0] > 100.0
        assert x_up[1] > 100.0
        # Covariance should decrease after measurement
        assert P_up[0, 0] < 4.0


# ===========================================================================
# 2. CT Model Tests
# ===========================================================================

class TestCTSubFilter:
    def test_ct_circular_prediction(self) -> None:
        """Verify CT model curves velocity according to turn rate omega."""
        dt = 0.1
        omega = math.pi / 2.0  # 90 deg/s
        ct = CTSubFilter(dt=dt, q_pos=0.01, q_vel=0.01, q_omega=0.01)
        # Heading east: vx=100, vy=0
        x_init = np.array([0.0, 0.0, 100.0, 0.0, omega], dtype=np.float64)
        P_init = np.eye(5, dtype=np.float64) * 10.0
        ct.set_state(x_init, P_init)

        x_pred, P_pred = ct.predict()
        # After turn, vy should become positive (curving) and vx should decrease
        assert x_pred[2] < 100.0  # vx decreased
        assert x_pred[3] > 0.0    # vy increased
        assert x_pred[4] == pytest.approx(omega)
        assert np.all(np.linalg.eigvals(P_pred) > 0)  # Positive definite

    def test_ct_small_turn_rate_stability(self) -> None:
        """Verify omega -> 0 produces exact constant-velocity kinematics without division by zero."""
        dt = 0.0333
        ct = CTSubFilter(dt=dt)
        for tiny_omega in [0.0, 1e-12, -1e-12, 1e-7, -1e-7]:
            x_init = np.array([100.0, 100.0, 60.0, -30.0, tiny_omega], dtype=np.float64)
            ct.set_state(x_init, np.eye(5) * 5.0)
            x_pred, P_pred = ct.predict()

            assert not np.isnan(x_pred).any()
            assert not np.isinf(x_pred).any()
            assert not np.isnan(P_pred).any()
            assert x_pred[0] == pytest.approx(100.0 + 60.0 * dt, rel=1e-4)
            assert x_pred[1] == pytest.approx(100.0 - 30.0 * dt, rel=1e-4)


# ===========================================================================
# 3. RW Model Tests
# ===========================================================================

class TestRWSubFilter:
    def test_rw_process_noise_scale(self) -> None:
        dt = 0.0333
        cv = CVSubFilter(dt=dt, q_pos=1.0, q_vel=2.0)
        rw = RWSubFilter(dt=dt, q_pos=1.0, q_vel=2.0, q_rw_factor=20.0)

        assert rw.Q[0, 0] == pytest.approx(cv.Q[0, 0] * 20.0)
        assert rw.Q[2, 2] == pytest.approx(cv.Q[2, 2] * 20.0)

    def test_rw_tracks_sharp_jumps(self) -> None:
        """Verify RW filter reacts faster than CV to an abrupt trajectory acceleration."""
        dt = 0.0333
        cv = CVSubFilter(dt=dt)
        rw = RWSubFilter(dt=dt, q_rw_factor=25.0)

        cv.set_state(np.array([100.0, 100.0, 0.0, 0.0]), np.eye(4) * 4.0)
        rw.set_state(np.array([100.0, 100.0, 0.0, 0.0]), np.eye(4) * 4.0)

        # Abrupt jump of 30 px
        z = np.array([130.0, 100.0])
        R = np.eye(2) * 4.0

        cv.predict()
        rw.predict()

        x_cv, _ = cv.update(z, R)
        x_rw, _ = rw.update(z, R)

        # RW must gain more velocity / position towards the step change
        assert x_rw[0] > x_cv[0]
        assert x_rw[2] > x_cv[2]


# ===========================================================================
# 4. IMM Interaction, Mixing, and Probability Update Tests
# ===========================================================================

class TestIMMTrackerCore:
    def test_imm_initialization(self) -> None:
        tracker = IMMTracker()
        tracker.init_track(200.0, 150.0, vx=10.0, vy=-5.0, confidence=0.9)

        state = tracker.get_state()
        assert state.x == 200.0
        assert state.y == 150.0
        assert state.vx == 10.0
        assert state.vy == -5.0
        assert state.confidence == 0.9
        assert state.locked is True
        assert state.dominant_model in ["CV", "CT", "RW"]
        assert pytest.approx(state.prob_cv + state.prob_ct + state.prob_rw) == 1.0

    def test_imm_interaction_mixing(self) -> None:
        tracker = IMMTracker()
        tracker.init_track(100.0, 100.0, vx=20.0, vy=10.0)

        # Force distinct states in sub-filters
        tracker.models[0].x = np.array([100.0, 100.0, 30.0, 0.0])
        tracker.models[1].x = np.array([105.0, 95.0, 0.0, 30.0, 0.5])
        tracker.models[2].x = np.array([98.0, 102.0, 10.0, 10.0])

        pos_pred = tracker.predict()
        assert isinstance(pos_pred, tuple)
        assert len(pos_pred) == 2
        # Position estimate should be finite and within the convex hull of sub-filters
        assert 90.0 < pos_pred[0] < 120.0
        assert 90.0 < pos_pred[1] < 120.0

    def test_imm_probability_update_straight_line(self) -> None:
        """Constant velocity trajectory should boost CV model probability."""
        dt = 1.0 / 30.0
        tracker = IMMTracker(dt=dt)
        tracker.init_track(100.0, 100.0, vx=50.0, vy=0.0)

        x, y = 100.0, 100.0
        for _ in range(30):
            x += 50.0 * dt
            tracker.predict()
            tracker.update(x, y, score=1.0)

        state = tracker.get_state()
        probs = tracker.model_probabilities
        # CV should be high and dominant for a pure constant-velocity line
        assert probs["CV"] > 0.40
        assert state.dominant_model == "CV"

    def test_imm_probability_update_turning(self) -> None:
        """Circular turning trajectory should elevate CT model probability."""
        dt = 1.0 / 30.0
        tracker = IMMTracker(dt=dt)
        cx, cy, r = 300.0, 300.0, 150.0
        omega = 1.0  # rad/s

        tracker.init_track(cx + r, cy, vx=0.0, vy=r * omega)

        for step in range(45):
            t = (step + 1) * dt
            meas_x = cx + r * math.cos(omega * t)
            meas_y = cy + r * math.sin(omega * t)
            tracker.predict()
            tracker.update(meas_x, meas_y, score=0.95)

        probs = tracker.model_probabilities
        # CT model probability should be strong on an ongoing curved trajectory
        assert probs["CT"] > 0.20

    def test_association_gate_outlier_rejection(self) -> None:
        tracker = IMMTracker()
        tracker.init_track(300.0, 300.0)

        assert tracker.is_within_gate(310.0, 310.0) is True   # dist ~14 px < 60 px
        assert tracker.is_within_gate(500.0, 500.0) is False  # dist ~282 px > 60 px

        # Candidate selection
        dets = [
            Detection(x=550.0, y=550.0, intensity=250.0, area_px=10.0, score=0.99), # Outlier
            Detection(x=305.0, y=304.0, intensity=200.0, area_px=10.0, score=0.90), # Target
        ]
        best = tracker.select_best_detection(dets)
        assert best is not None
        assert best.x == 305.0

    def test_coasting_during_occlusion(self) -> None:
        """Coasting propagates velocity without crashing or resetting."""
        dt = 1.0 / 30.0
        tracker = IMMTracker(dt=dt)
        tracker.init_track(100.0, 100.0, vx=60.0, vy=0.0)

        for _ in range(5):
            tracker.predict()
            state = tracker.coast()

        # Expected x = 100 + 60 * (5 * 1/30) = 110 px
        assert abs(state.x - 110.0) < 1.0
        assert state.locked is True
        assert state.confidence < 0.8  # Confidence decays during occlusion

    def test_long_horizon_numerical_stability(self) -> None:
        """Run 1,000 steps with alternating straight, turning, and noisy maneuvers."""
        dt = 1.0 / 30.0
        tracker = IMMTracker(dt=dt)
        tracker.init_track(200.0, 200.0)

        x, y = 200.0, 200.0
        rng = np.random.RandomState(42)

        for i in range(1000):
            tracker.predict()
            # Alternating dynamics
            if i < 300:
                x += 30.0 * dt
            elif i < 600:
                angle = (i - 300) * dt * 0.8
                x += 40.0 * math.cos(angle) * dt
                y += 40.0 * math.sin(angle) * dt
            else:
                x += rng.randn() * 2.0
                y += rng.randn() * 2.0

            meas_x = x + rng.randn() * 1.0
            meas_y = y + rng.randn() * 1.0
            state = tracker.update(meas_x, meas_y, score=0.9)

            assert not math.isnan(state.x)
            assert not math.isnan(state.y)
            assert not math.isnan(state.vx)
            assert not math.isnan(state.vy)
            assert state.prob_cv >= 0.0
            assert state.prob_ct >= 0.0
            assert state.prob_rw >= 0.0
            assert pytest.approx(state.prob_cv + state.prob_ct + state.prob_rw) == 1.0
