"""
Built-in Plugin Presets for NETRA Plugin Playground.
Contains pure-Python baseline and experimental algorithms for Vision, Tracking, and Control slots.
"""

import math
import numpy as np
from typing import Optional, Dict, Any

# ============================================================================
# TRACKING PRESETS
# ============================================================================

def alpha_beta_tracking(measurement: Optional[Dict[str, Any]], dt: float, state: Dict[str, Any], ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, float]:
    """
    Fixed-gain Alpha-Beta Filter for tracking position and velocity.
    Params: alpha (default 0.85), beta (default 0.005)
    """
    alpha = float(params.get("alpha", 0.85))
    beta = float(params.get("beta", 0.005))

    if "x" not in state:
        if measurement is None:
            return {"x": 320.0, "y": 240.0, "vx": 0.0, "vy": 0.0}
        state["x"] = float(measurement["x"])
        state["y"] = float(measurement["y"])
        state["vx"] = 0.0
        state["vy"] = 0.0
        return {"x": state["x"], "y": state["y"], "vx": 0.0, "vy": 0.0}

    # Predict
    pred_x = state["x"] + state["vx"] * dt
    pred_y = state["y"] + state["vy"] * dt

    if measurement is not None:
        res_x = float(measurement["x"]) - pred_x
        res_y = float(measurement["y"]) - pred_y
        state["x"] = pred_x + alpha * res_x
        state["y"] = pred_y + alpha * res_y
        state["vx"] = state["vx"] + (beta / dt) * res_x
        state["vy"] = state["vy"] + (beta / dt) * res_y
    else:
        state["x"] = pred_x
        state["y"] = pred_y

    return {"x": state["x"], "y": state["y"], "vx": state["vx"], "vy": state["vy"]}


def ema_tracking(measurement: Optional[Dict[str, Any]], dt: float, state: Dict[str, Any], ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, float]:
    """
    Exponential Moving Average (EMA) position tracking with finite-difference velocity.
    Params: alpha (default 0.6)
    """
    alpha = float(params.get("alpha", 0.6))

    if "x" not in state:
        if measurement is None:
            return {"x": 320.0, "y": 240.0, "vx": 0.0, "vy": 0.0}
        state["x"] = float(measurement["x"])
        state["y"] = float(measurement["y"])
        state["vx"] = 0.0
        state["vy"] = 0.0
        return {"x": state["x"], "y": state["y"], "vx": 0.0, "vy": 0.0}

    if measurement is not None:
        mx, my = float(measurement["x"]), float(measurement["y"])
        new_x = alpha * mx + (1.0 - alpha) * state["x"]
        new_y = alpha * my + (1.0 - alpha) * state["y"]
        state["vx"] = (new_x - state["x"]) / max(dt, 1e-4)
        state["vy"] = (new_y - state["y"]) / max(dt, 1e-4)
        state["x"] = new_x
        state["y"] = new_y
    else:
        # Coast using current velocity estimate
        state["x"] += state["vx"] * dt
        state["y"] += state["vy"] * dt

    return {"x": state["x"], "y": state["y"], "vx": state["vx"], "vy": state["vy"]}


def single_kalman_tracking(measurement: Optional[Dict[str, Any]], dt: float, state: Dict[str, Any], ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, float]:
    """
    Single Constant-Velocity 4D Kalman Filter (X, Y, VX, VY).
    Params: process_noise (default 10.0), meas_noise (default 2.0)
    """
    q_val = float(params.get("process_noise", 10.0))
    r_val = float(params.get("meas_noise", 2.0))

    if "x_hat" not in state:
        if measurement is None:
            return {"x": 320.0, "y": 240.0, "vx": 0.0, "vy": 0.0}
        init_x = float(measurement["x"])
        init_y = float(measurement["y"])
        state["x_hat"] = np.array([[init_x], [init_y], [0.0], [0.0]], dtype=float)
        state["P"] = np.eye(4, dtype=float) * 100.0

    x_hat = state["x_hat"]
    P = state["P"]

    # F transition matrix
    F = np.array([
        [1.0, 0.0,  dt, 0.0],
        [0.0, 1.0, 0.0,  dt],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ])
    Q = np.eye(4, dtype=float) * q_val * dt
    H = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ])
    R = np.eye(2, dtype=float) * r_val

    # Predict
    x_hat = F @ x_hat
    P = F @ P @ F.T + Q

    # Update if measurement available
    if measurement is not None:
        z = np.array([[float(measurement["x"])], [float(measurement["y"])]])
        y_res = z - H @ x_hat
        S = H @ P @ H.T + R
        K = P @ H.T @ np.linalg.inv(S)
        x_hat = x_hat + K @ y_res
        P = (np.eye(4) - K @ H) @ P

    state["x_hat"] = x_hat
    state["P"] = P

    return {
        "x": float(x_hat[0, 0]),
        "y": float(x_hat[1, 0]),
        "vx": float(x_hat[2, 0]),
        "vy": float(x_hat[3, 0]),
    }


def pda_tracking(measurement: Optional[Dict[str, Any]], dt: float, state: Dict[str, Any], ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, float]:
    """
    Probabilistic Data Association (PDA) Filter using candidate detections from ctx["candidates"].
    Demonstrates research paper mapping (Bar-Shalom PDA).
    Params: gate_gamma (default 9.0), pd (default 0.9)
    """
    gate_gamma = float(params.get("gate_gamma", 9.0))
    pd_prob = float(params.get("pd", 0.9))

    if "x_hat" not in state:
        if measurement is None:
            return {"x": 320.0, "y": 240.0, "vx": 0.0, "vy": 0.0}
        state["x_hat"] = np.array([[float(measurement["x"])], [float(measurement["y"])], [0.0], [0.0]])
        state["P"] = np.eye(4) * 50.0

    x_hat = state["x_hat"]
    P = state["P"]

    F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
    H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
    Q = np.eye(4) * 5.0 * dt
    R = np.eye(2) * 3.0

    # Predict
    x_hat = F @ x_hat
    P = F @ P @ F.T + Q

    candidates = ctx.get("candidates", [])
    if candidates:
        S = H @ P @ H.T + R
        S_inv = np.linalg.inv(S)
        validated = []
        for cand in candidates:
            z = np.array([[cand["x"]], [cand["y"]]])
            nu = z - H @ x_hat
            d2 = float(nu.T @ S_inv @ nu)
            if d2 <= gate_gamma:
                validated.append((z, nu, d2))

        if validated:
            # Calculate association probabilities (simplified PDA)
            weights = [math.exp(-0.5 * d2) for _, _, d2 in validated]
            sum_w = sum(weights) + (1.0 - pd_prob)
            beta_0 = (1.0 - pd_prob) / sum_w
            betas = [w / sum_w for w in weights]

            combined_nu = np.zeros((2, 1))
            for b, (_, nu, _) in zip(betas, validated):
                combined_nu += b * nu

            K = P @ H.T @ S_inv
            x_hat = x_hat + K @ combined_nu
            P = (np.eye(4) - (1.0 - beta_0) * (K @ H)) @ P

    state["x_hat"] = x_hat
    state["P"] = P

    return {
        "x": float(x_hat[0, 0]),
        "y": float(x_hat[1, 0]),
        "vx": float(x_hat[2, 0]),
        "vy": float(x_hat[3, 0]),
    }


# ============================================================================
# CONTROL PRESETS
# ============================================================================

def p_only_control(error: Dict[str, float], velocity: Dict[str, float], dt: float, state: Dict[str, Any], ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, float]:
    """
    Pure Proportional Controller (no Integral, Derivative, or Feedforward).
    Params: kp (default 1.8)
    """
    kp = float(params.get("kp", 1.8))
    px_per_deg_x = float(ctx.get("px_per_deg_x", 160.0))
    px_per_deg_y = float(ctx.get("px_per_deg_y", 160.0))

    pan_rate = (kp * error["ex"]) / px_per_deg_x
    tilt_rate = (kp * error["ey"]) / px_per_deg_y

    return {"pan_rate": pan_rate, "tilt_rate": tilt_rate}


def bang_bang_control(error: Dict[str, float], velocity: Dict[str, float], dt: float, state: Dict[str, Any], ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, float]:
    """
    Bang-Bang (Relay) Controller with deadband.
    Params: deadband_px (default 5.0), max_rate (default 15.0)
    """
    db = float(params.get("deadband_px", 5.0))
    max_rate = float(params.get("max_rate", 15.0))

    ex, ey = error["ex"], error["ey"]
    pan_rate = 0.0
    if abs(ex) > db:
        pan_rate = max_rate if ex > 0 else -max_rate

    tilt_rate = 0.0
    if abs(ey) > db:
        tilt_rate = max_rate if ey > 0 else -max_rate

    return {"pan_rate": pan_rate, "tilt_rate": tilt_rate}


def lead_lag_control(error: Dict[str, float], velocity: Dict[str, float], dt: float, state: Dict[str, Any], ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, float]:
    """
    Discrete Lead-Lag Compensator.
    Params: gain (default 2.0), alpha (default 0.2), T (default 0.05)
    """
    gain = float(params.get("gain", 2.0))
    alpha = float(params.get("alpha", 0.2))
    T = float(params.get("T", 0.05))
    px_per_deg_x = float(ctx.get("px_per_deg_x", 160.0))
    px_per_deg_y = float(ctx.get("px_per_deg_y", 160.0))

    # Bilinear transform coefficient: a = (2*alpha*T - dt) / (2*alpha*T + dt)
    # b0 = (2*T + dt) / (2*alpha*T + dt), b1 = (dt - 2*T) / (2*alpha*T + dt)
    denom = 2.0 * alpha * T + dt
    a1 = (2.0 * alpha * T - dt) / denom
    b0 = (2.0 * T + dt) / denom
    b1 = (dt - 2.0 * T) / denom

    if "prev_ex" not in state:
        state["prev_ex"] = error["ex"]
        state["prev_ey"] = error["ey"]
        state["prev_ux"] = 0.0
        state["prev_uy"] = 0.0

    ex, ey = error["ex"], error["ey"]
    ux = a1 * state["prev_ux"] + b0 * ex + b1 * state["prev_ex"]
    uy = a1 * state["prev_uy"] + b0 * ey + b1 * state["prev_ey"]

    state["prev_ex"] = ex
    state["prev_ey"] = ey
    state["prev_ux"] = ux
    state["prev_uy"] = uy

    pan_rate = gain * ux / px_per_deg_x
    tilt_rate = gain * uy / px_per_deg_y

    return {"pan_rate": pan_rate, "tilt_rate": tilt_rate}


def rl_cascaded_pid_control(error: Dict[str, float], velocity: Dict[str, float], dt: float, state: Dict[str, Any], ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, float]:
    """
    Cascaded Position and Velocity PID Controller for Optical Deflector / Gimbal Positioning.
    Tuned via Deep Deterministic Policy Gradient (DDPG) Reinforcement Learning.
    Reference: Prikhodko et al., "Precision positioning in free-space optical communication systems via PID control tuned by RL", arXiv:2607.15910 (July 2026).
    
    Six coefficients: {Pp, Ip, Dp, Pv, Iv, Dv} applied to coordinate and speed PID controllers:
      - a_opt1 (Table II): Pp=4.602, Ip=0.08649, Dp=12.29, Pv=3.238, Iv=0.0004861, Dv=14.34
      - a_opt2 (Table II): Pp=4.676, Ip=0.08508, Dp=12.95, Pv=3.119, Iv=0.0004785, Dv=15.32
      - abaseline (Table III): Pp=4.0, Ip=0.07, Dp=20.0, Pv=3.0, Iv=0.0004, Dv=20.0
    """
    variant = str(params.get("variant", "opt1")).lower()
    if variant == "opt2":
        default_Pp, default_Ip, default_Dp = 4.676, 0.08508, 12.95
        default_Pv, default_Iv, default_Dv = 3.119, 0.0004785, 15.32
    elif variant == "baseline":
        default_Pp, default_Ip, default_Dp = 4.0, 0.07, 20.0
        default_Pv, default_Iv, default_Dv = 3.0, 0.0004, 20.0
    else:  # opt1
        default_Pp, default_Ip, default_Dp = 4.602, 0.08649, 12.29
        default_Pv, default_Iv, default_Dv = 3.238, 0.0004861, 14.34

    Pp = float(params.get("Pp", default_Pp))
    Ip = float(params.get("Ip", default_Ip))
    Dp = float(params.get("Dp", default_Dp))
    Pv = float(params.get("Pv", default_Pv))
    Iv = float(params.get("Iv", default_Iv))
    Dv = float(params.get("Dv", default_Dv))

    px_per_deg_x = float(ctx.get("px_per_deg_x", 160.0))
    px_per_deg_y = float(ctx.get("px_per_deg_y", 160.0))
    dt_clamped = max(float(dt), 1e-4)

    ex = float(error.get("ex", 0.0))
    ey = float(error.get("ey", 0.0))

    # 1. Position PID Loop (Coordinates)
    int_ex = state.get("int_ex", 0.0) + ex * dt_clamped
    int_ex = max(-60.0, min(60.0, int_ex))
    prev_ex = state.get("prev_ex", ex)
    dex = (ex - prev_ex) / dt_clamped
    state["int_ex"] = int_ex
    state["prev_ex"] = ex

    int_ey = state.get("int_ey", 0.0) + ey * dt_clamped
    int_ey = max(-60.0, min(60.0, int_ey))
    prev_ey = state.get("prev_ey", ey)
    dey = (ey - prev_ey) / dt_clamped
    state["int_ey"] = int_ey
    state["prev_ey"] = ey

    v_cmd_x = Pp * ex + Ip * int_ex + Dp * dex
    v_cmd_y = Pp * ey + Ip * int_ey + Dp * dey

    # 2. Velocity PID Loop (Speeds)
    vx_meas = float(velocity.get("vx", 0.0))
    vy_meas = float(velocity.get("vy", 0.0))

    e_vx = v_cmd_x - vx_meas
    e_vy = v_cmd_y - vy_meas

    int_evx = state.get("int_evx", 0.0) + e_vx * dt_clamped
    int_evx = max(-100.0, min(100.0, int_evx))
    prev_evx = state.get("prev_evx", e_vx)
    devx = (e_vx - prev_evx) / dt_clamped
    state["int_evx"] = int_evx
    state["prev_evx"] = e_vx

    int_evy = state.get("int_evy", 0.0) + e_vy * dt_clamped
    int_evy = max(-100.0, min(100.0, int_evy))
    prev_evy = state.get("prev_evy", e_vy)
    devy = (e_vy - prev_evy) / dt_clamped
    state["int_evy"] = int_evy
    state["prev_evy"] = e_vy

    u_x = Pv * e_vx + Iv * int_evx + Dv * devx
    u_y = Pv * e_vy + Iv * int_evy + Dv * devy

    pan_rate = u_x / px_per_deg_x
    tilt_rate = u_y / px_per_deg_y

    return {"pan_rate": pan_rate, "tilt_rate": tilt_rate}


# ============================================================================
# VISION PRESETS
# ============================================================================

def simple_threshold_vision(image: np.ndarray, width: int, height: int, ctx: Dict[str, Any], params: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """
    Fixed Intensity Threshold Vision detector.
    Params: threshold (default 180)
    """
    thresh = float(params.get("threshold", 180.0))
    y_idx, x_idx = np.where(image >= thresh)
    if len(x_idx) == 0:
        return None

    # Center of mass of thresholded region
    mean_x = float(np.mean(x_idx))
    mean_y = float(np.mean(y_idx))
    max_val = float(np.max(image[y_idx, x_idx]))

    return {"x": mean_x, "y": mean_y, "confidence": min(1.0, max_val / 255.0)}


def adaptive_threshold_vision(image: np.ndarray, width: int, height: int, ctx: Dict[str, Any], params: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """
    Adaptive Local Thresholding Vision detector (handles non-uniform illumination/fog).
    Params: block_size (default 31), C (default 10)
    """
    import cv2
    block_size = int(params.get("block_size", 31))
    if block_size % 2 == 0:
        block_size += 1
    C_val = float(params.get("C", 10.0))

    binary = cv2.adaptiveThreshold(
        image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, C_val
    )
    y_idx, x_idx = np.where(binary > 0)
    if len(x_idx) == 0:
        return None

    # Pick brightest spot within binary mask
    vals = image[y_idx, x_idx]
    best = np.argmax(vals)
    return {"x": float(x_idx[best]), "y": float(y_idx[best]), "confidence": float(vals[best] / 255.0)}


def psf_fit_vision(image: np.ndarray, width: int, height: int, ctx: Dict[str, Any], params: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """
    Gaussian PSF fitting Vision detector (Sub-pixel accuracy).
    Params: window_size (default 11)
    """
    w_size = int(params.get("window_size", 11))
    max_y, max_x = np.unravel_index(np.argmax(image), image.shape)
    peak_val = image[max_y, max_x]

    if peak_val < 100:
        return None

    half = w_size // 2
    y0, y1 = max(0, max_y - half), min(height, max_y + half + 1)
    x0, x1 = max(0, max_x - half), min(width, max_x + half + 1)
    patch = image[y0:y1, x0:x1].astype(float)

    # Sub-pixel centroid in local patch
    total = np.sum(patch)
    if total < 1e-5:
        return {"x": float(max_x), "y": float(max_y), "confidence": float(peak_val / 255.0)}

    grid_y, grid_x = np.ogrid[0:patch.shape[0], 0:patch.shape[1]]
    cx = np.sum(grid_x * patch) / total + x0
    cy = np.sum(grid_y * patch) / total + y0

    return {"x": float(cx), "y": float(cy), "confidence": min(1.0, float(peak_val / 255.0))}


PRESET_CATALOG = {
    "tracking": {
        "NETRA Default (IMM)": None,  # Signals default adapter
        "Alpha-Beta Filter": alpha_beta_tracking,
        "Single Kalman Filter": single_kalman_tracking,
        "EMA Smoother": ema_tracking,
        "PDA Filter (Bar-Shalom)": pda_tracking,
    },
    "control": {
        "NETRA Default (PID+FF)": None,
        "P-Only Controller": p_only_control,
        "Bang-Bang Controller": bang_bang_control,
        "Lead-Lag Compensator": lead_lag_control,
    },
    "vision": {
        "NETRA Default (CNN+Spot)": None,
        "Simple Threshold": simple_threshold_vision,
        "Adaptive Threshold": adaptive_threshold_vision,
        "Gaussian PSF Fit": psf_fit_vision,
    },
}
