"""
src/fsoc/tracking/imm.py
========================
Interacting Multiple Model (IMM) State Estimator for Mobile FSOC Terminals.

Replaces single Kalman filter with a 3-model estimator combining:
1. Constant Velocity (CV)   - Straight line & low-acceleration cruising
2. Constant Turn Rate (CT)  - Circular & figure-8 orbital trajectories
3. Random Walk (RW)         - Sudden platform motion, severe jitter & abrupt maneuvers

Features:
- Primary centroid position updates from classical/CNN detector
- Auxiliary short-term velocity updates from local sparse Lucas-Kanade optical flow
- Seamless drop-in interface for PID controller & tracking state machine
"""
from __future__ import annotations
from typing import Optional
import numpy as np

from ..core.types import TrackState, Detection, Point, FlowResult
from ..core.config import TrackingConfig, AppConfig
from ..vision.flow_gating import AdaptiveFlowGater
from .models import CVSubFilter, CTSubFilter, RWSubFilter


MODEL_NAMES = ["CV", "CT", "RW"]


class IMMTracker:
    """
    3-Model Interacting Multiple Model (IMM) Estimator.
    Drop-in replacement for KalmanTracker with superior trajectory adaptability,
    adaptive optical flow confidence gating, and smooth velocity deweighting.
    """
    def __init__(
        self,
        cfg: TrackingConfig | AppConfig | None = None,
        dt: float = 1.0 / 30.0,
    ) -> None:
        if cfg is None:
            t_cfg = TrackingConfig()
        elif isinstance(cfg, AppConfig):
            t_cfg = cfg.tracking
            dt = cfg.pipeline.dt
        elif isinstance(cfg, TrackingConfig):
            t_cfg = cfg
        else:
            raise TypeError(f"Unsupported config type: {type(cfg)}")

        self.cfg = t_cfg
        self.dt = float(dt)

        # Base measurement noise covariance R0
        self._r0 = float(self.cfg.r_pos)

        # Adaptive flow reliability and confidence gater
        self.flow_gater = AdaptiveFlowGater(self.cfg.adaptive_flow, dt=self.dt)

        # 1. Initialize Sub-Filters
        self.models = [
            CVSubFilter(dt=self.dt, q_pos=self.cfg.q_pos, q_vel=self.cfg.q_vel),
            CTSubFilter(
                dt=self.dt,
                q_pos=self.cfg.q_pos,
                q_vel=self.cfg.q_vel,
                q_omega=self.cfg.imm_q_ct_omega,
            ),
            RWSubFilter(
                dt=self.dt,
                q_pos=self.cfg.q_pos,
                q_vel=self.cfg.q_vel,
                q_rw_factor=self.cfg.imm_q_rw_factor,
            ),
        ]
        self.num_models = 3

        # 2. Transition Probability Matrix Pi [3x3]
        raw_trans = self.cfg.imm_transition_matrix
        self.Pi = np.array(raw_trans, dtype=np.float64)
        for i in range(self.num_models):
            row_sum = np.sum(self.Pi[i])
            if row_sum > 0:
                self.Pi[i] /= row_sum
            else:
                self.Pi[i] = np.ones(self.num_models) / self.num_models

        # 3. Model Probabilities mu [3]
        raw_probs = self.cfg.imm_init_probs
        self.mu = np.array(raw_probs, dtype=np.float64)
        self.mu /= np.sum(self.mu)
        self.c_bar = np.zeros(self.num_models, dtype=np.float64)

        # 4. Combined State and Covariance (in viewport pixel space)
        self.x = np.zeros(4, dtype=np.float64)  # [x, y, vx, vy]
        self.P = np.eye(4, dtype=np.float64) * 100.0

        # Diagnostics / Telemetry
        self.last_innovation = 0.0
        self.last_nis = 0.0
        self.last_uncertainty = 10.0
        self.last_flow: Optional[FlowResult] = None

        # Internal tracking status
        self.is_initialized: bool = False
        self.is_locked: bool = False
        self.confidence: float = 0.0
        self.coast_frames: int = 0
        self.total_updates: int = 0

    @property
    def R0(self) -> float:
        """Base measurement noise variance."""
        return self._r0

    @R0.setter
    def R0(self, val: float) -> None:
        self._r0 = float(val)

    @property
    def dominant_model(self) -> str:
        """Name of the currently dominant motion model."""
        idx = int(np.argmax(self.mu))
        return MODEL_NAMES[idx]

    @property
    def model_probabilities(self) -> dict[str, float]:
        """Dictionary of current model probabilities."""
        return {
            "CV": float(self.mu[0]),
            "CT": float(self.mu[1]),
            "RW": float(self.mu[2]),
        }

    def init_track(
        self,
        x: float,
        y: float,
        vx: float = 0.0,
        vy: float = 0.0,
        confidence: float = 0.8,
    ) -> None:
        """Initialize or reset track with a confirmed detection."""
        x4 = np.array([x, y, vx, vy], dtype=np.float64)
        P4 = np.diag([self._r0, self._r0, 500.0, 500.0]).astype(np.float64)

        x5 = np.array([x, y, vx, vy, 0.0], dtype=np.float64)
        P5 = np.diag([self._r0, self._r0, 500.0, 500.0, 1.0]).astype(np.float64)

        self.models[0].set_state(x4, P4)
        self.models[1].set_state(x5, P5)
        self.models[2].set_state(x4, P4)

        raw_probs = self.cfg.imm_init_probs
        self.mu = np.array(raw_probs, dtype=np.float64)
        self.mu /= np.sum(self.mu)

        self.x = x4.copy()
        self.P = P4.copy()

        self.is_initialized = True
        self.is_locked = True
        self.confidence = float(np.clip(confidence, 0.0, 1.0))
        self.coast_frames = 0
        self.total_updates = 1
        self.last_innovation = 0.0
        self.last_nis = 0.0
        self.last_uncertainty = float(np.sqrt(P4[0, 0] + P4[1, 1]))
        self.last_flow = None

    def predict(self) -> tuple[float, float]:
        """
        Execute Step 1 (Interaction / Mixing) and Step 2 (Model Prediction).
        Returns predicted combined position (x_pred, y_pred).
        """
        if not self.is_initialized:
            return (0.0, 0.0)

        # 1. Model Interaction / Mixing
        self.c_bar = np.zeros(self.num_models, dtype=np.float64)
        for j in range(self.num_models):
            self.c_bar[j] = np.sum(self.Pi[:, j] * self.mu)
            self.c_bar[j] = max(self.c_bar[j], 1e-12)

        mu_mix = np.zeros((self.num_models, self.num_models), dtype=np.float64)
        for i in range(self.num_models):
            for j in range(self.num_models):
                mu_mix[i, j] = (self.Pi[i, j] * self.mu[i]) / self.c_bar[j]

        states_4d = [m.x[:4] for m in self.models]
        covs_4d = [m.P[:4, :4] for m in self.models]

        for j in range(self.num_models):
            x_0j_4d = np.zeros(4, dtype=np.float64)
            for i in range(self.num_models):
                x_0j_4d += mu_mix[i, j] * states_4d[i]

            P_0j_4d = np.zeros((4, 4), dtype=np.float64)
            for i in range(self.num_models):
                dx = (states_4d[i] - x_0j_4d).reshape(-1, 1)
                P_0j_4d += mu_mix[i, j] * (covs_4d[i] + dx @ dx.T)

            if j == 1:
                omega_0 = self.models[1].x[4]
                x_0j_5d = np.array([x_0j_4d[0], x_0j_4d[1], x_0j_4d[2], x_0j_4d[3], omega_0], dtype=np.float64)
                P_0j_5d = np.zeros((5, 5), dtype=np.float64)
                P_0j_5d[:4, :4] = P_0j_4d
                P_0j_5d[4, 4] = self.models[1].P[4, 4]
                P_0j_5d[:4, 4] = mu_mix[1, 1] * self.models[1].P[:4, 4]
                P_0j_5d[4, :4] = P_0j_5d[:4, 4]
                self.models[1].set_state(x_0j_5d, P_0j_5d)
            else:
                self.models[j].set_state(x_0j_4d, P_0j_4d)

        # 2. Model-Specific Predictions
        for m in self.models:
            m.predict()

        # Compute combined predicted state for gating & control
        x_pred_comb = np.zeros(4, dtype=np.float64)
        for j in range(self.num_models):
            x_pred_comb += self.c_bar[j] * self.models[j].x[:4]

        self.x = x_pred_comb
        return (float(self.x[0]), float(self.x[1]))

    def gate_distance(self, meas_x: float, meas_y: float) -> float:
        """Euclidean distance from current predicted position to candidate measurement."""
        if not self.is_initialized:
            return 0.0
        return float(np.hypot(meas_x - self.x[0], meas_y - self.x[1]))

    def is_within_gate(self, meas_x: float, meas_y: float) -> bool:
        """Check if measurement falls within association gate."""
        return self.gate_distance(meas_x, meas_y) <= self.cfg.gate_dist_px

    def select_best_detection(
        self, detections: list[Detection]
    ) -> Optional[Detection]:
        """
        Select best detection candidate within tracking gate.
        Prefers detections close to predicted location with high CNN verification score.
        """
        if not detections:
            return None

        if not self.is_initialized:
            return detections[0]

        best_det: Optional[Detection] = None
        min_cost = float("inf")

        for det in detections:
            dist = self.gate_distance(det.x, det.y)
            if dist <= self.cfg.gate_dist_px:
                cost = dist / (1.0 + 2.0 * det.score)
                if cost < min_cost:
                    min_cost = cost
                    best_det = det

        return best_det

    def update(
        self,
        meas_x: float,
        meas_y: float,
        score: float = 1.0,
        flow: Optional[FlowResult] = None,
    ) -> TrackState:
        """
        Update IMM with position observation [meas_x, meas_y] and optional optical flow velocity.
        """
        if not self.is_initialized:
            self.init_track(meas_x, meas_y, confidence=score)
            return self.get_state()

        z = np.array([meas_x, meas_y], dtype=np.float64)

        # Scale position measurement noise R inversely with detection score
        r_eff = self._r0 / max(0.2, score)
        R = np.eye(2, dtype=np.float64) * r_eff

        # 1. Evaluate adaptive optical flow reliability & confidence weight
        flow_eval = self.flow_gater.evaluate_flow(
            flow,
            pred_vx=float(self.x[2]),
            pred_vy=float(self.x[3]),
            pred_var_vx=float(self.P[2, 2]),
            pred_var_vy=float(self.P[3, 3]),
        )

        has_valid_flow = flow_eval.valid and flow_eval.weight > 0.0
        if has_valid_flow:
            z_vel = np.array([flow_eval.vx_viewport, flow_eval.vy_viewport], dtype=np.float64)
            # Adaptively scaled measurement variance: R_vel_eff = R_vel_base / max(flow_weight, epsilon)
            sigma_v2_base = 2.0 * self._r0 / (self.dt ** 2)
            r_v_eff = sigma_v2_base / max(1e-6, flow_eval.weight)
            R_vel = np.eye(2, dtype=np.float64) * r_v_eff

        likelihoods = np.zeros(self.num_models, dtype=np.float64)
        innovations = []
        nises = []

        for j in range(self.num_models):
            lik_pos, y_res, S_cov, nis_pos = self.models[j].compute_likelihood(z, R)
            innovations.append(y_res)
            nises.append(nis_pos)

            if has_valid_flow:
                lik_vel, _, _, nis_vel = self.models[j].compute_velocity_likelihood(z_vel, R_vel)
                if nis_vel < self.cfg.adaptive_flow.nis_gate:
                    likelihoods[j] = lik_pos * lik_vel
                else:
                    likelihoods[j] = lik_pos
            else:
                likelihoods[j] = lik_pos

        # 2. Update Model Probabilities
        c_denom = float(np.sum(likelihoods * self.c_bar))
        if c_denom > 1e-12:
            self.mu = (likelihoods * self.c_bar) / c_denom
        else:
            self.mu = self.c_bar.copy()

        self.mu = np.clip(self.mu, 1e-4, 1.0)
        self.mu /= np.sum(self.mu)

        # 3. Model-Specific Measurement Updates
        for j in range(self.num_models):
            # Primary position update
            self.models[j].update(z, R)
            # Auxiliary velocity update if valid flow exists and passes gating
            if has_valid_flow:
                _, _, _, nis_vel = self.models[j].compute_velocity_likelihood(z_vel, R_vel)
                if nis_vel < self.cfg.adaptive_flow.nis_gate:
                    self.models[j].update_velocity(z_vel, R_vel)

        # 4. State Combination
        states_4d = [m.x[:4] for m in self.models]
        covs_4d = [m.P[:4, :4] for m in self.models]

        x_comb = np.zeros(4, dtype=np.float64)
        for j in range(self.num_models):
            x_comb += self.mu[j] * states_4d[j]

        P_comb = np.zeros((4, 4), dtype=np.float64)
        for j in range(self.num_models):
            dx = (states_4d[j] - x_comb).reshape(-1, 1)
            P_comb += self.mu[j] * (covs_4d[j] + dx @ dx.T)

        self.x = x_comb
        self.P = 0.5 * (P_comb + P_comb.T)

        # 5. Diagnostics
        comb_inv = np.zeros(2, dtype=np.float64)
        comb_nis = 0.0
        for j in range(self.num_models):
            comb_inv += self.mu[j] * np.abs(innovations[j])
            comb_nis += self.mu[j] * nises[j]

        self.last_innovation = float(np.linalg.norm(comb_inv))
        self.last_nis = float(comb_nis)
        self.last_uncertainty = float(np.sqrt(max(0.0, self.P[0, 0] + self.P[1, 1])))
        self.last_flow = flow_eval

        # 6. Status and Quality
        self.coast_frames = 0
        self.is_locked = True
        self.total_updates += 1

        inv_quality = max(0.0, 1.0 - self.last_innovation / self.cfg.gate_dist_px)
        self.confidence = float(np.clip(
            0.7 * self.confidence + 0.3 * (0.5 * inv_quality + 0.5 * score),
            0.0, 1.0
        ))

        return self.get_state()

    def coast(self, flow: Optional[FlowResult] = None) -> TrackState:
        """
        Coast IMM track forward when measurement is missing (temporary occlusion).
        Maintains model probabilities along Markov chain while decaying confidence.
        If valid flow is available during occlusion, auxiliary velocity is fused adaptively.
        """
        if not self.is_initialized:
            return self.get_state()

        if np.sum(self.c_bar) > 0:
            self.mu = self.c_bar / np.sum(self.c_bar)

        flow_eval = self.flow_gater.evaluate_flow(
            flow,
            pred_vx=float(self.x[2]),
            pred_vy=float(self.x[3]),
            pred_var_vx=float(self.P[2, 2]),
            pred_var_vy=float(self.P[3, 3]),
        )

        has_valid_flow = flow_eval.valid and flow_eval.weight > 0.0
        if has_valid_flow:
            z_vel = np.array([flow_eval.vx_viewport, flow_eval.vy_viewport], dtype=np.float64)
            sigma_v2_base = 2.0 * self._r0 / (self.dt ** 2)
            r_v_eff = sigma_v2_base / max(1e-6, flow_eval.weight)
            R_vel = np.eye(2, dtype=np.float64) * r_v_eff
            for j in range(self.num_models):
                _, _, _, nis_vel = self.models[j].compute_velocity_likelihood(z_vel, R_vel)
                if nis_vel < self.cfg.adaptive_flow.nis_gate:
                    self.models[j].update_velocity(z_vel, R_vel)

        states_4d = [m.x[:4] for m in self.models]
        covs_4d = [m.P[:4, :4] for m in self.models]

        x_comb = np.zeros(4, dtype=np.float64)
        for j in range(self.num_models):
            x_comb += self.mu[j] * states_4d[j]

        P_comb = np.zeros((4, 4), dtype=np.float64)
        for j in range(self.num_models):
            dx = (states_4d[j] - x_comb).reshape(-1, 1)
            P_comb += self.mu[j] * (covs_4d[j] + dx @ dx.T)

        self.x = x_comb
        self.P = 0.5 * (P_comb + P_comb.T)

        self.coast_frames += 1
        self.confidence = float(max(0.0, self.confidence * 0.90))

        if self.coast_frames > self.cfg.max_coast_frames:
            self.is_locked = False

        self.last_uncertainty = float(np.sqrt(max(0.0, self.P[0, 0] + self.P[1, 1])))
        self.last_flow = flow_eval
        return self.get_state()

    def get_state(self) -> TrackState:
        """Return current IMM state as a TrackState dataclass."""
        flow = self.last_flow
        return TrackState(
            x=float(self.x[0]),
            y=float(self.x[1]),
            vx=float(self.x[2]),
            vy=float(self.x[3]),
            confidence=float(self.confidence),
            locked=bool(self.is_locked),
            prob_cv=float(self.mu[0]),
            prob_ct=float(self.mu[1]),
            prob_rw=float(self.mu[2]),
            dominant_model=self.dominant_model,
            innovation=float(self.last_innovation),
            uncertainty=float(self.last_uncertainty),
            flow_valid=bool(flow.valid) if flow is not None else False,
            flow_dx=float(flow.dx_viewport) if flow is not None else 0.0,
            flow_dy=float(flow.dy_viewport) if flow is not None else 0.0,
            flow_speed=float(flow.speed) if flow is not None else 0.0,
            flow_confidence=float(flow.confidence) if flow is not None else 0.0,
            flow_feature_count=int(flow.feature_count) if flow is not None else 0,
            flow_fb_error=float(flow.fb_error_mean) if flow is not None else 0.0,
            flow_weight=float(flow.weight) if flow is not None else 0.0,
            flow_quality=float(flow.quality) if flow is not None else 0.0,
            flow_innovation=float(flow.innovation) if flow is not None else 0.0,
            jitter_score=float(flow.jitter_score) if flow is not None else 0.0,
            flow_gate_reason=str(flow.gate_reason) if flow is not None else "NO_FLOW",
        )

    def reset(self) -> None:
        """Reset tracker state."""
        self.x = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 100.0
        self.is_initialized = False
        self.is_locked = False
        self.confidence = 0.0
        self.coast_frames = 0
        self.total_updates = 0
        self.last_innovation = 0.0
        self.last_nis = 0.0
        self.last_uncertainty = 10.0
        self.last_flow = None
        self.flow_gater.reset()

        raw_probs = self.cfg.imm_init_probs
        self.mu = np.array(raw_probs, dtype=np.float64)
        self.mu /= np.sum(self.mu)

        for m in self.models:
            m.x = np.zeros(m.dim_x, dtype=np.float64)
            m.P = np.eye(m.dim_x, dtype=np.float64) * 100.0
