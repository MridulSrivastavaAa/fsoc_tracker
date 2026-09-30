"""
src/fsoc/tracking/kalman.py
===========================
4-State Linear Kalman Filter for Beacon Trajectory Estimation & Coasting.
State vector: x = [x, y, vx, vy]^T (position in viewport px, velocity in px/s).

Features:
- Continuous White Noise Acceleration (CWNA) process model
- Dynamic measurement covariance scaled by CNN verification score
- Association gating (Mahalanobis / Euclidean distance)
- Coasting through atmospheric occlusions (clouds, smoke, turbulence dropouts)
"""
from __future__ import annotations
from typing import Optional
import numpy as np

from ..core.types import TrackState, Detection, Point
from ..core.config import TrackingConfig, AppConfig


class KalmanTracker:
    """
    Kalman filter estimator for beacon tracking in camera viewport coordinates.
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

        # State transition matrix F
        self.F = np.array([
            [1.0, 0.0, self.dt, 0.0],
            [0.0, 1.0, 0.0, self.dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)

        # Measurement matrix H
        self.H = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ], dtype=np.float64)

        # Process noise covariance Q (CWNA model)
        dt2 = self.dt ** 2
        dt3 = self.dt ** 3
        q_p = self.cfg.q_pos
        q_v = self.cfg.q_vel

        self.Q = np.array([
            [dt3 / 3.0 * q_p, 0.0, dt2 / 2.0 * q_p, 0.0],
            [0.0, dt3 / 3.0 * q_p, 0.0, dt2 / 2.0 * q_p],
            [dt2 / 2.0 * q_p, 0.0, self.dt * q_v, 0.0],
            [0.0, dt2 / 2.0 * q_p, 0.0, self.dt * q_v],
        ], dtype=np.float64)

        # Base measurement noise covariance R0
        self.R0 = self.cfg.r_pos

        # State vector x and covariance P
        self.x = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 100.0

        # Internal tracking status
        self.is_initialized: bool = False
        self.is_locked: bool = False
        self.confidence: float = 0.0
        self.coast_frames: int = 0
        self.total_updates: int = 0

    def init_track(
        self,
        x: float,
        y: float,
        vx: float = 0.0,
        vy: float = 0.0,
        confidence: float = 0.8,
    ) -> None:
        """Initialize or reset track with a confirmed detection."""
        self.x = np.array([x, y, vx, vy], dtype=np.float64)
        # Higher initial velocity uncertainty so PID doesn't get a huge spike
        self.P = np.diag([self.R0, self.R0, 500.0, 500.0]).astype(np.float64)
        self.is_initialized = True
        self.is_locked = True
        self.confidence = float(np.clip(confidence, 0.0, 1.0))
        self.coast_frames = 0
        self.total_updates = 1

    def predict(self) -> tuple[float, float]:
        """
        Predict state forward by dt.
        Returns predicted position (x_pred, y_pred).
        """
        if not self.is_initialized:
            return (0.0, 0.0)

        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q
        return (float(self.x[0]), float(self.x[1]))

    def gate_distance(self, meas_x: float, meas_y: float) -> float:
        """Euclidean distance from current predicted position to measurement."""
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
        Prefers detections close to predicted location with high score.
        """
        if not detections:
            return None

        if not self.is_initialized:
            # If not initialized, return candidate with highest prominence
            return detections[0]

        best_det: Optional[Detection] = None
        min_cost = float("inf")

        for det in detections:
            dist = self.gate_distance(det.x, det.y)
            if dist <= self.cfg.gate_dist_px:
                # Combined cost: distance penalized, higher score rewarded
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
        Update Kalman filter with observation z = [meas_x, meas_y].
        """
        if not self.is_initialized:
            self.init_track(meas_x, meas_y, confidence=score)
            return self.get_state()

        z = np.array([meas_x, meas_y], dtype=np.float64)

        # Scale R inversely with confidence score (higher score = lower noise)
        r_eff = self.R0 / max(0.2, score)
        R = np.eye(2, dtype=np.float64) * r_eff

        # Innovation (residual)
        y = z - np.dot(self.H, self.x)
        S = np.dot(np.dot(self.H, self.P), self.H.T) + R

        # Kalman gain K
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))

        # State update
        self.x = self.x + np.dot(K, y)

        # Covariance update (Joseph form for numerical stability)
        I_KH = np.eye(4, dtype=np.float64) - np.dot(K, self.H)
        self.P = np.dot(np.dot(I_KH, self.P), I_KH.T) + np.dot(np.dot(K, R), K.T)

        # Reset coast counter and update track quality
        self.coast_frames = 0
        self.is_locked = True
        self.total_updates += 1

        # Innovation-based confidence
        residual_norm = float(np.linalg.norm(y))
        inv_quality = max(0.0, 1.0 - residual_norm / self.cfg.gate_dist_px)
        self.confidence = float(np.clip(0.7 * self.confidence + 0.3 * (0.5 * inv_quality + 0.5 * score), 0.0, 1.0))

        return self.get_state()

    def coast(self, flow: Optional[FlowResult] = None) -> TrackState:
        """
        Coast track forward when measurement is missing (temporary occlusion).
        Uses estimated velocity to extrapolate position while decaying confidence.
        """
        if not self.is_initialized:
            return self.get_state()

        self.coast_frames += 1
        # Confidence decay during occlusion
        self.confidence = float(max(0.0, self.confidence * 0.90))

        if self.coast_frames > self.cfg.max_coast_frames:
            self.is_locked = False

        return self.get_state()

    def get_state(self) -> TrackState:
        """Return current Kalman filter state as a TrackState dataclass."""
        return TrackState(
            x=float(self.x[0]),
            y=float(self.x[1]),
            vx=float(self.x[2]),
            vy=float(self.x[3]),
            confidence=float(self.confidence),
            locked=bool(self.is_locked),
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
