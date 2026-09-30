"""
src/fsoc/tracking/models.py
===========================
Individual Model Sub-Filters for the IMM (Interacting Multiple Model) Estimator.

Models:
1. CVSubFilter: Constant Velocity (CWNA kinematic process model)
2. CTSubFilter: Coordinated / Constant Turn Rate (EKF with Taylor expansion for small omega)
3. RWSubFilter: Random Walk / High-Maneuver (High process noise for abrupt drift & jitter)

Supports both primary centroid position measurements and auxiliary optical-flow velocity updates.
"""
from __future__ import annotations
import math
import numpy as np


class CVSubFilter:
    """
    Constant Velocity (CV) 4-State Kalman Filter.
    State: x = [x, y, vx, vy]^T (position in px, velocity in px/s).
    """
    def __init__(self, dt: float, q_pos: float = 1.0, q_vel: float = 2.0) -> None:
        self.dt = float(dt)
        self.q_pos = float(q_pos)
        self.q_vel = float(q_vel)

        self.dim_x = 4
        self.dim_z = 2

        self.x = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 100.0

        # State transition matrix F
        self.F = np.array([
            [1.0, 0.0, self.dt, 0.0],
            [0.0, 1.0, 0.0, self.dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)

        # Measurement matrix H for position
        self.H = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ], dtype=np.float64)

        # Measurement matrix H_v for velocity
        self.H_v = np.array([
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)

        # Process noise covariance Q (CWNA model)
        dt2 = self.dt ** 2
        dt3 = self.dt ** 3
        self.Q = np.array([
            [dt3 / 3.0 * self.q_pos, 0.0, dt2 / 2.0 * self.q_pos, 0.0],
            [0.0, dt3 / 3.0 * self.q_pos, 0.0, dt2 / 2.0 * self.q_pos],
            [dt2 / 2.0 * self.q_pos, 0.0, self.dt * self.q_vel, 0.0],
            [0.0, dt2 / 2.0 * self.q_pos, 0.0, self.dt * self.q_vel],
        ], dtype=np.float64)

    def set_state(self, x: np.ndarray, P: np.ndarray) -> None:
        """Set mixed state and covariance."""
        self.x = np.array(x[:4], dtype=np.float64, copy=True)
        self.P = np.array(P[:4, :4], dtype=np.float64, copy=True)

    def predict(self) -> tuple[np.ndarray, np.ndarray]:
        """Predict forward by dt."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.x, self.P

    def compute_likelihood(
        self, z: np.ndarray, R: np.ndarray
    ) -> tuple[float, np.ndarray, np.ndarray, float]:
        """
        Compute Gaussian measurement likelihood, innovation residual, innovation covariance, and NIS.
        Returns: (likelihood, y, S, nis)
        """
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + R
        det_s = S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0]
        det_s = max(det_s, 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)

        nis = float(y @ S_inv @ y)
        nis = max(0.0, nis)

        denom = 2.0 * math.pi * math.sqrt(det_s)
        likelihood = math.exp(-0.5 * min(nis, 100.0)) / max(denom, 1e-12)
        likelihood = max(likelihood, 1e-12)

        return likelihood, y, S, nis

    def update(self, z: np.ndarray, R: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Update filter with position observation z and measurement noise R using Joseph form."""
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + R
        det_s = max(S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0], 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)

        K = self.P @ self.H.T @ S_inv
        self.x = self.x + K @ y

        I_KH = np.eye(4, dtype=np.float64) - K @ self.H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T
        self.P = 0.5 * (self.P + self.P.T)
        return self.x, self.P

    def compute_velocity_likelihood(
        self, z_vel: np.ndarray, R_vel: np.ndarray
    ) -> tuple[float, np.ndarray, np.ndarray, float]:
        """Compute Gaussian likelihood for auxiliary velocity observation (from Optical Flow)."""
        y = z_vel - self.H_v @ self.x
        S = self.H_v @ self.P @ self.H_v.T + R_vel
        det_s = max(S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0], 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)
        nis = float(max(0.0, y @ S_inv @ y))
        denom = 2.0 * math.pi * math.sqrt(det_s)
        likelihood = max(1e-12, math.exp(-0.5 * min(nis, 100.0)) / max(denom, 1e-12))
        return likelihood, y, S, nis

    def update_velocity(self, z_vel: np.ndarray, R_vel: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Update filter state with auxiliary velocity observation (from Optical Flow)."""
        y = z_vel - self.H_v @ self.x
        S = self.H_v @ self.P @ self.H_v.T + R_vel
        det_s = max(S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0], 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)
        K = self.P @ self.H_v.T @ S_inv
        self.x = self.x + K @ y
        I_KH = np.eye(4, dtype=np.float64) - K @ self.H_v
        self.P = I_KH @ self.P @ I_KH.T + K @ R_vel @ K.T
        self.P = 0.5 * (self.P + self.P.T)
        return self.x, self.P


class CTSubFilter:
    """
    Coordinated / Constant Turn Rate (CT) 5-State Extended Kalman Filter.
    State: x = [x, y, vx, vy, omega]^T (position in px, velocity in px/s, turn rate in rad/s).
    Formulated with high-order Taylor series expansions for omega -> 0 to ensure 100% numerical stability.
    """
    def __init__(
        self,
        dt: float,
        q_pos: float = 1.0,
        q_vel: float = 2.0,
        q_omega: float = 0.8,
    ) -> None:
        self.dt = float(dt)
        self.q_pos = float(q_pos)
        self.q_vel = float(q_vel)
        self.q_omega = float(q_omega)

        self.dim_x = 5
        self.dim_z = 2

        self.x = np.zeros(5, dtype=np.float64)
        self.P = np.eye(5, dtype=np.float64) * 100.0

        self.H = np.array([
            [1.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0, 0.0],
        ], dtype=np.float64)

        self.H_v = np.array([
            [0.0, 0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0, 0.0],
        ], dtype=np.float64)

        # Process noise covariance Q_ct
        dt2 = self.dt ** 2
        dt3 = self.dt ** 3
        self.Q = np.zeros((5, 5), dtype=np.float64)
        self.Q[0, 0] = dt3 / 3.0 * self.q_pos
        self.Q[1, 1] = dt3 / 3.0 * self.q_pos
        self.Q[0, 2] = dt2 / 2.0 * self.q_pos
        self.Q[2, 0] = dt2 / 2.0 * self.q_pos
        self.Q[1, 3] = dt2 / 2.0 * self.q_pos
        self.Q[3, 1] = dt2 / 2.0 * self.q_pos
        self.Q[2, 2] = self.dt * self.q_vel
        self.Q[3, 3] = self.dt * self.q_vel
        self.Q[4, 4] = self.dt * self.q_omega

    def set_state(self, x: np.ndarray, P: np.ndarray) -> None:
        """Set mixed state and covariance."""
        self.x = np.array(x, dtype=np.float64, copy=True)
        self.P = np.array(P, dtype=np.float64, copy=True)

    def predict(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Nonlinear state prediction and Jacobian covariance propagation.
        Handles omega -> 0 via Taylor expansion.
        """
        px, py, vx, vy, omega = self.x
        dt = self.dt
        theta = omega * dt

        # Stable trigonometric coefficients
        if abs(omega) > 1e-5:
            sin_t = math.sin(theta)
            cos_t = math.cos(theta)
            A = sin_t / omega
            B = (1.0 - cos_t) / omega
            C = cos_t
            S = sin_t

            # Derivatives w.r.t omega
            dA = (theta * cos_t - sin_t) / (omega ** 2)
            dB = (theta * sin_t - (1.0 - cos_t)) / (omega ** 2)
        else:
            # Taylor series expansions around omega = 0
            theta2 = theta * theta
            theta3 = theta2 * theta
            theta4 = theta3 * theta
            theta5 = theta4 * theta

            A = dt * (1.0 - theta2 / 6.0 + theta4 / 120.0)
            B = dt * (theta / 2.0 - theta3 / 24.0 + theta5 / 720.0)
            C = 1.0 - theta2 / 2.0 + theta4 / 24.0
            S = theta - theta3 / 6.0 + theta5 / 120.0

            dA = (dt ** 2) * (-theta / 3.0 + theta3 / 30.0)
            dB = (dt ** 2) * (0.5 - theta2 / 8.0 + theta4 / 144.0)

        # State transition
        px_new = px + A * vx - B * vy
        py_new = py + B * vx + A * vy
        vx_new = C * vx - S * vy
        vy_new = S * vx + C * vy
        omega_new = omega

        self.x = np.array([px_new, py_new, vx_new, vy_new, omega_new], dtype=np.float64)

        # Jacobian F = df/dx
        dx_domega = dA * vx - dB * vy
        dy_domega = dB * vx + dA * vy
        dvx_domega = -dt * (S * vx + C * vy)
        dvy_domega = dt * (C * vx - S * vy)

        F = np.array([
            [1.0, 0.0, A, -B, dx_domega],
            [0.0, 1.0, B, A, dy_domega],
            [0.0, 0.0, C, -S, dvx_domega],
            [0.0, 0.0, S, C, dvy_domega],
            [0.0, 0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)

        self.P = F @ self.P @ F.T + self.Q
        self.P = 0.5 * (self.P + self.P.T)
        return self.x, self.P

    def compute_likelihood(
        self, z: np.ndarray, R: np.ndarray
    ) -> tuple[float, np.ndarray, np.ndarray, float]:
        """Compute Gaussian likelihood, innovation, innovation covariance, and NIS."""
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + R
        det_s = S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0]
        det_s = max(det_s, 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)

        nis = float(y @ S_inv @ y)
        nis = max(0.0, nis)

        denom = 2.0 * math.pi * math.sqrt(det_s)
        likelihood = math.exp(-0.5 * min(nis, 100.0)) / max(denom, 1e-12)
        likelihood = max(likelihood, 1e-12)

        return likelihood, y, S, nis

    def update(self, z: np.ndarray, R: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Update CT filter with position observation z using Joseph form."""
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + R
        det_s = max(S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0], 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)

        K = self.P @ self.H.T @ S_inv
        self.x = self.x + K @ y

        I_KH = np.eye(5, dtype=np.float64) - K @ self.H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T
        self.P = 0.5 * (self.P + self.P.T)
        return self.x, self.P

    def compute_velocity_likelihood(
        self, z_vel: np.ndarray, R_vel: np.ndarray
    ) -> tuple[float, np.ndarray, np.ndarray, float]:
        """Compute Gaussian likelihood for auxiliary velocity observation."""
        y = z_vel - self.H_v @ self.x
        S = self.H_v @ self.P @ self.H_v.T + R_vel
        det_s = max(S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0], 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)
        nis = float(max(0.0, y @ S_inv @ y))
        denom = 2.0 * math.pi * math.sqrt(det_s)
        likelihood = max(1e-12, math.exp(-0.5 * min(nis, 100.0)) / max(denom, 1e-12))
        return likelihood, y, S, nis

    def update_velocity(self, z_vel: np.ndarray, R_vel: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Update CT filter state with auxiliary velocity observation (from Optical Flow)."""
        y = z_vel - self.H_v @ self.x
        S = self.H_v @ self.P @ self.H_v.T + R_vel
        det_s = max(S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0], 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)
        K = self.P @ self.H_v.T @ S_inv
        self.x = self.x + K @ y
        I_KH = np.eye(5, dtype=np.float64) - K @ self.H_v
        self.P = I_KH @ self.P @ I_KH.T + K @ R_vel @ K.T
        self.P = 0.5 * (self.P + self.P.T)
        return self.x, self.P


class RWSubFilter:
    """
    Random Walk (RW) / High-Maneuver 4-State Kalman Filter.
    State: x = [x, y, vx, vy]^T (position in px, velocity in px/s).
    Uses elevated process noise to aggressively track sharp turns, jitter, and platform drift.
    """
    def __init__(
        self,
        dt: float,
        q_pos: float = 1.0,
        q_vel: float = 2.0,
        q_rw_factor: float = 20.0,
    ) -> None:
        self.dt = float(dt)
        self.q_pos = float(q_pos) * float(q_rw_factor)
        self.q_vel = float(q_vel) * float(q_rw_factor)

        self.dim_x = 4
        self.dim_z = 2

        self.x = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 100.0

        self.F = np.array([
            [1.0, 0.0, self.dt, 0.0],
            [0.0, 1.0, 0.0, self.dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)

        self.H = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ], dtype=np.float64)

        self.H_v = np.array([
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)

        dt2 = self.dt ** 2
        dt3 = self.dt ** 3
        self.Q = np.array([
            [dt3 / 3.0 * self.q_pos, 0.0, dt2 / 2.0 * self.q_pos, 0.0],
            [0.0, dt3 / 3.0 * self.q_pos, 0.0, dt2 / 2.0 * self.q_pos],
            [dt2 / 2.0 * self.q_pos, 0.0, self.dt * self.q_vel, 0.0],
            [0.0, dt2 / 2.0 * self.q_pos, 0.0, self.dt * self.q_vel],
        ], dtype=np.float64)

    def set_state(self, x: np.ndarray, P: np.ndarray) -> None:
        """Set mixed state and covariance."""
        self.x = np.array(x[:4], dtype=np.float64, copy=True)
        self.P = np.array(P[:4, :4], dtype=np.float64, copy=True)

    def predict(self) -> tuple[np.ndarray, np.ndarray]:
        """Predict forward by dt."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.x, self.P

    def compute_likelihood(
        self, z: np.ndarray, R: np.ndarray
    ) -> tuple[float, np.ndarray, np.ndarray, float]:
        """Compute Gaussian likelihood, innovation, innovation covariance, and NIS."""
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + R
        det_s = S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0]
        det_s = max(det_s, 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)

        nis = float(y @ S_inv @ y)
        nis = max(0.0, nis)

        denom = 2.0 * math.pi * math.sqrt(det_s)
        likelihood = math.exp(-0.5 * min(nis, 100.0)) / max(denom, 1e-12)
        likelihood = max(likelihood, 1e-12)

        return likelihood, y, S, nis

    def update(self, z: np.ndarray, R: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Update RW filter with position observation z using Joseph form."""
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + R
        det_s = max(S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0], 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)

        K = self.P @ self.H.T @ S_inv
        self.x = self.x + K @ y

        I_KH = np.eye(4, dtype=np.float64) - K @ self.H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T
        self.P = 0.5 * (self.P + self.P.T)
        return self.x, self.P

    def compute_velocity_likelihood(
        self, z_vel: np.ndarray, R_vel: np.ndarray
    ) -> tuple[float, np.ndarray, np.ndarray, float]:
        """Compute Gaussian likelihood for auxiliary velocity observation."""
        y = z_vel - self.H_v @ self.x
        S = self.H_v @ self.P @ self.H_v.T + R_vel
        det_s = max(S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0], 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)
        nis = float(max(0.0, y @ S_inv @ y))
        denom = 2.0 * math.pi * math.sqrt(det_s)
        likelihood = max(1e-12, math.exp(-0.5 * min(nis, 100.0)) / max(denom, 1e-12))
        return likelihood, y, S, nis

    def update_velocity(self, z_vel: np.ndarray, R_vel: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Update RW filter state with auxiliary velocity observation (from Optical Flow)."""
        y = z_vel - self.H_v @ self.x
        S = self.H_v @ self.P @ self.H_v.T + R_vel
        det_s = max(S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0], 1e-12)
        S_inv = np.array([
            [S[1, 1] / det_s, -S[0, 1] / det_s],
            [-S[1, 0] / det_s, S[0, 0] / det_s],
        ], dtype=np.float64)
        K = self.P @ self.H_v.T @ S_inv
        self.x = self.x + K @ y
        I_KH = np.eye(4, dtype=np.float64) - K @ self.H_v
        self.P = I_KH @ self.P @ I_KH.T + K @ R_vel @ K.T
        self.P = 0.5 * (self.P + self.P.T)
        return self.x, self.P
