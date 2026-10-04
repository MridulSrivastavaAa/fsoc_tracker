"""
Contract Reference Constants and Template Code Strings for NETRA Plugins.
"""
import math
from typing import Any

VISION_CONTRACT_DOC = '''def detect(image, width, height, ctx, params):
    """
    ================================================================================
    VISION PLUGIN CONTRACT: Target Beacon Detection & Centroiding
    ================================================================================
    INPUT PARAMETERS:
        image  : numpy.ndarray (2D uint8, shape: height x width, values 0..255)
                 Raw grayscale telescope sensor frame containing beacon and sky noise.
        width  : int (typically 640) - Frame width in pixels.
        height : int (typically 480) - Frame height in pixels.
        ctx    : dict - Telemetry context (frame_index, timestamp_s, cam_cx, cam_cy,
                 scintillation, atmosphere).
        params : dict - Tunable hyperparameters accessed via params.get().

    OUTPUT:
        dict: {"x": float, "y": float, "confidence": float}
        OR None if no target spot is detected / target occluded.
        Coordinates x, y are sub-pixel positions in viewport pixels [0..width, 0..height].
    ================================================================================
    """
'''

TRACKING_CONTRACT_DOC = '''def track(measurement, dt, state, ctx, params):
    """
    ================================================================================
    TRACKING PLUGIN CONTRACT: State Estimation & Trajectory Filtering
    ================================================================================
    INPUT PARAMETERS:
        measurement : dict {"x": float, "y": float, "confidence": float} or None
                      Sub-pixel centroid measurement from Vision stage, or None if lost.
        dt          : float - Elapsed time step in seconds (~0.0333 s at 30 FPS).
        state       : dict - Persistent dictionary preserved across simulation frames.
        ctx         : dict - Telemetry (cam_cx, cam_cy, frame_index, timestamp_s,
                      fsm_state, atmosphere, candidates).
        params      : dict - Tunable hyperparameters accessed via params.get().

    OUTPUT:
        dict: {"x": float, "y": float, "vx": float, "vy": float}
        x, y in viewport pixels; vx, vy in viewport pixels per second.
    ================================================================================
    """
'''

CONTROL_CONTRACT_DOC = '''def control(error, velocity, dt, state, ctx, params):
    """
    ================================================================================
    CONTROL PLUGIN CONTRACT: Gimbal Pan/Tilt Angular Rate Servo Loop
    ================================================================================
    INPUT PARAMETERS:
        error    : dict {"ex": float, "ey": float} - Tracking error in viewport pixels
                   relative to boresight optical center (320, 240).
        velocity : dict {"vx": float, "vy": float} - Estimated target velocity in px/s.
        dt       : float - Elapsed time step in seconds (~0.0333 s at 30 FPS).
        state    : dict - Persistent dictionary preserved across simulation frames.
        ctx      : dict - Telemetry (px_per_deg_x, px_per_deg_y, pan_deg, tilt_deg,
                   max_pan_rate, max_tilt_rate, fsm_state).
        params   : dict - Tunable hyperparameters accessed via params.get().

    OUTPUT:
        dict: {"pan_rate": float, "tilt_rate": float}
        Commanded gimbal angular velocities in degrees per second (deg/s).
    ================================================================================
    """
'''

VISION_TEMPLATE = '''def detect(image, width, height, ctx, params):
    """
    ================================================================================
    VISION PLUGIN CONTRACT: Target Beacon Detection & Centroiding
    ================================================================================
    INPUT PARAMETERS EXPLANATION:
    --------------------------------------------------------------------------------
    1. image (numpy.ndarray):
       - 2D array of shape (height, width) with dtype uint8 (values from 0 to 255).
       - Grayscale frame captured directly by the telescope camera sensor.
       - Contains background sky, turbulence scintillation, haze, noise, and beacon spot.
       - Access pixel at row y (0..height-1), col x (0..width-1) via: image[y, x].

    2. width (int):
       - Frame width in viewport pixels (typically 640).

    3. height (int):
       - Frame height in viewport pixels (typically 480).

    4. ctx (dict):
       - Real-time engine telemetry and optical context:
         - ctx["frame_index"]   (int)  : Monotonically increasing frame counter (0, 1, 2, ...).
         - ctx["timestamp_s"]   (float): Elapsed mission time in seconds.
         - ctx["cam_cx"]        (float): Optical principal center X in pixels (320.0).
         - ctx["cam_cy"]        (float): Optical principal center Y in pixels (240.0).
         - ctx["scintillation"] (float): Atmospheric turbulence scintillation variance.
         - ctx["atmosphere"]    (str)  : Current weather condition ("clear", "fog", "rain", etc.).

    5. params (dict):
       - User-tunable hyperparameters extracted via params.get("param_name", default_val).
       * NOTE: Any params.get() defined here automatically creates a live tuning slider in the GUI!
    ================================================================================
    """
    import numpy as np

    # ── [1. DEMO CODE: FETCH HYPERPARAMETERS] ─────────────────────────────────
    # Live sliders are auto-discovered from these calls:
    threshold = params.get("threshold", 180)    # Intensity threshold cutoff (0 to 255)
    min_area = params.get("min_area", 1)        # Minimum active pixels to consider valid

    # ── [2. DEMO CODE: INTENSITY THRESHOLDING & MASK CREATION] ────────────────
    mask = image >= threshold
    if not np.any(mask):
        # Target not visible or below intensity threshold -> return None to signal loss
        return None

    # ── [3. DEMO CODE: SUB-PIXEL INTENSITY CENTROIDING (Center of Gravity)] ──
    y_coords, x_coords = np.where(mask)
    if len(x_coords) < min_area:
        return None

    weights = image[y_coords, x_coords].astype(float)
    total_w = np.sum(weights)
    if total_w < 1e-5:
        return None

    # Compute intensity-weighted centroid for sub-pixel accuracy
    cx = float(np.sum(x_coords * weights) / total_w)
    cy = float(np.sum(y_coords * weights) / total_w)
    confidence = min(1.0, float(np.max(weights) / 255.0))

    # ── [4. RETURN CONTRACT] ──────────────────────────────────────────────────
    # OUTPUT EXPLANATION:
    # --------------------------------------------------------------------------
    # Return EITHER:
    #   A dictionary with exact keys "x", "y", "confidence":
    #     - "x"          (float): Sub-pixel horizontal position in image pixels (0.0 to width).
    #     - "y"          (float): Sub-pixel vertical position in image pixels (0.0 to height).
    #     - "confidence" (float): Detection quality score between 0.0 (low) and 1.0 (high).
    #   OR:
    #     None: Indicating target is occluded, lost, or below detection threshold.
    # * What the engine does: Constructs a Detection object for the Tracking filter to consume.
    # --------------------------------------------------------------------------
    return {
        "x": cx,
        "y": cy,
        "confidence": confidence,
    }
'''

TRACKING_TEMPLATE = '''def track(measurement, dt, state, ctx, params):
    """
    ================================================================================
    TRACKING PLUGIN CONTRACT: State Estimation & Trajectory Filtering
    ================================================================================
    INPUT PARAMETERS EXPLANATION:
    --------------------------------------------------------------------------------
    1. measurement (dict or None):
       - If target is detected by the Vision stage:
         - measurement["x"] (float): Measured horizontal spot centroid in pixels (0.0 to width).
         - measurement["y"] (float): Measured vertical spot centroid in pixels (0.0 to height).
         - measurement["confidence"] (float): Blob detection confidence score (0.0 to 1.0).
       - If target is occluded, lost, or obscured by clouds/haze/noise: None.
       * Objective: Smooth noise when measurement is present; coast when measurement is None.

    2. dt (float):
       - Elapsed time since the last tracking update in seconds (~0.0333 s at 30 Hz).
       * Used to project kinematic state forward: predicted_pos = pos + velocity * dt.

    3. state (dict):
       - Persistent memory dictionary preserved across all simulation frames for this plugin.
       * Stores internal filter variables: estimated position, velocity, covariances, flags.
       * Initialized on the first frame when "x" not in state.

    4. ctx (dict):
       - Real-time engine telemetry and sensor calibration context:
         - ctx["cam_cx"]      (float): Optical boresight center X in pixels (320.0).
         - ctx["cam_cy"]      (float): Optical boresight center Y in pixels (240.0).
         - ctx["frame_index"] (int)  : Monotonically increasing frame counter (0, 1, 2, ...).
         - ctx["timestamp_s"] (float): Elapsed mission time in seconds.
         - ctx["fsm_state"]   (str)  : Current engine state ("TRACK", "ACQUIRE", "LOST").
         - ctx["atmosphere"]  (str)  : Atmospheric weather condition ("clear", "fog", etc.).
         - ctx["candidates"]  (list) : Alternative detection candidates in the current frame.

    5. params (dict):
       - User-tunable hyperparameters extracted via params.get("param_name", default_val).
       * NOTE: Any params.get() defined here automatically creates a live tuning slider in the GUI!
    ================================================================================
    """
    # ── [1. DEMO CODE: FETCH HYPERPARAMETERS] ─────────────────────────────────
    # Live sliders are auto-discovered from these calls:
    alpha = params.get("alpha", 0.85)       # Position innovation weight (0.0 to 1.0)
    beta = params.get("beta", 0.005)        # Velocity innovation gain (> 0.0)

    cam_cx = ctx.get("cam_cx", 320.0)
    cam_cy = ctx.get("cam_cy", 240.0)
    dt_c = max(float(dt), 1e-4)

    # ── [2. DEMO CODE: INITIALIZE STATE ON FIRST FRAME] ──────────────────────
    if "x" not in state:
        if measurement is None:
            # Fallback to boresight center with zero velocity
            return {"x": cam_cx, "y": cam_cy, "vx": 0.0, "vy": 0.0}
        state["x"] = float(measurement["x"])
        state["y"] = float(measurement["y"])
        state["vx"] = 0.0
        state["vy"] = 0.0
        return {"x": state["x"], "y": state["y"], "vx": 0.0, "vy": 0.0}

    # ── [3. DEMO CODE: TIME UPDATE / KINEMATIC PREDICTION] ───────────────────
    pred_x = state["x"] + state["vx"] * dt_c
    pred_y = state["y"] + state["vy"] * dt_c

    # ── [4. DEMO CODE: MEASUREMENT UPDATE OR COASTING] ────────────────────────
    if measurement is not None:
        # Innovation residual: difference between actual measurement and prediction
        res_x = float(measurement["x"]) - pred_x
        res_y = float(measurement["y"]) - pred_y

        # Alpha-Beta correction update
        state["x"] = pred_x + alpha * res_x
        state["y"] = pred_y + alpha * res_y
        state["vx"] = state["vx"] + (beta / dt_c) * res_x
        state["vy"] = state["vy"] + (beta / dt_c) * res_y
    else:
        # Measurement lost: coast smoothly on previous velocity without sudden jumps
        state["x"] = pred_x
        state["y"] = pred_y

    # ── [5. RETURN CONTRACT] ──────────────────────────────────────────────────
    # OUTPUT EXPLANATION:
    # --------------------------------------------------------------------------
    # Return a dictionary with exact keys "x", "y", "vx", "vy":
    #   - "x"  (float): Filtered horizontal target position in image coordinates [0..width].
    #   - "y"  (float): Filtered vertical target position in image coordinates [0..height].
    #   - "vx" (float): Estimated horizontal target velocity in pixels/second.
    #   - "vy" (float): Estimated vertical target velocity in pixels/second.
    # * What the engine does: Feeds x, y, vx, vy into the Control servo loop and evaluates lock status.
    # --------------------------------------------------------------------------
    return {
        "x": float(state["x"]),
        "y": float(state["y"]),
        "vx": float(state["vx"]),
        "vy": float(state["vy"]),
    }
'''

CONTROL_TEMPLATE = '''def control(error, velocity, dt, state, ctx, params):
    """
    ================================================================================
    CONTROL PLUGIN CONTRACT: Gimbal Pan/Tilt Angular Rate Servo Loop
    ================================================================================
    INPUT PARAMETERS EXPLANATION:
    --------------------------------------------------------------------------------
    1. error (dict):
       - error["ex"] (float): Horizontal boresight tracking error in pixels.
                              Defined as: (target_x - camera_center_x).
                              Positive (+) means target is to the RIGHT of optical axis.
                              Negative (-) means target is to the LEFT of optical axis.
       - error["ey"] (float): Vertical boresight tracking error in pixels.
                              Defined as: (target_y - camera_center_y).
                              Positive (+) means target is BELOW optical axis.
                              Negative (-) means target is ABOVE optical axis.
       * Objective: Drive both ex and ey to 0.0 to keep the beacon on the detector.

    2. velocity (dict):
       - velocity["vx"] (float): Estimated target velocity along X in image plane (pixels/s).
       - velocity["vy"] (float): Estimated target velocity along Y in image plane (pixels/s).
       * Used for derivative/damping action and feedforward tracking of high-speed trajectories.

    3. dt (float):
       - Time step elapsed since the last control execution in seconds (nominal: ~0.0333 s at 30 Hz).
       * Crucial for discrete-time numerical integration (error * dt) and differentiation (de / dt).

    4. state (dict):
       - Persistent memory dictionary preserved across all simulation frames for this plugin.
       * Use state to store loop integrators, previous errors, and filter history between frames.
       * e.g., state["int_ex"], state["prev_ex"], state["initialized"].

    5. ctx (dict):
       - Real-time engine telemetry and sensor calibration context:
         - ctx["px_per_deg_x"] (float): Pixels per physical degree along azimuth (~160.0 px/deg).
         - ctx["px_per_deg_y"] (float): Pixels per physical degree along elevation (~160.0 px/deg).
         - ctx["pan_deg"]      (float): Current physical pan gimbal angle in degrees.
         - ctx["tilt_deg"]     (float): Current physical tilt gimbal angle in degrees.
         - ctx["max_pan_rate"] (float): Motor safety velocity limit for pan (deg/s).
         - ctx["max_tilt_rate"](float): Motor safety velocity limit for tilt (deg/s).
         - ctx["fsm_state"]    (str)  : Finite State Machine mode ("TRACK", "ACQUIRE", "LOST").

    6. params (dict):
       - User-tunable hyperparameters extracted via params.get("param_name", default_val).
       * NOTE: Any params.get() defined here automatically creates a live tuning slider in the GUI!
    ================================================================================
    """
    # ── [1. DEMO CODE: FETCH HYPERPARAMETERS] ─────────────────────────────────
    # Live sliders are auto-discovered from these calls:
    Pp = params.get("Pp", 4.602)            # Position proportional gain
    Ip = params.get("Ip", 0.0865)           # Position integral gain
    Dp = params.get("Dp", 12.29)            # Position derivative gain
    Pv = params.get("Pv", 3.238)            # Velocity loop proportional gain
    Iv = params.get("Iv", 0.000486)         # Velocity loop integral gain
    Dv = params.get("Dv", 14.34)            # Velocity loop derivative gain

    # Read sensor geometry and safe time step
    px_per_deg_x = ctx.get("px_per_deg_x", 160.0)
    px_per_deg_y = ctx.get("px_per_deg_y", 160.0)
    dt_c = max(float(dt), 1e-4)

    # ── [2. DEMO CODE: EXTRACT INPUTS] ───────────────────────────────────────
    ex = float(error.get("ex", 0.0))
    ey = float(error.get("ey", 0.0))
    vx_meas = float(velocity.get("vx", 0.0))
    vy_meas = float(velocity.get("vy", 0.0))

    # ── [3. DEMO CODE: CASCADED POSITION PID LOOP] ───────────────────────────
    # Integrate position error with anti-windup clamping [-60, +60] px*s
    state["int_ex"] = max(-60.0, min(60.0, state.get("int_ex", 0.0) + ex * dt_c))
    state["int_ey"] = max(-60.0, min(60.0, state.get("int_ey", 0.0) + ey * dt_c))

    # Position error derivative
    dex = (ex - state.get("prev_ex", ex)) / dt_c
    dey = (ey - state.get("prev_ey", ey)) / dt_c
    state["prev_ex"] = ex
    state["prev_ey"] = ey

    # Desired pixel velocity command
    v_cmd_x = Pp * ex + Ip * state["int_ex"] + Dp * dex
    v_cmd_y = Pp * ey + Ip * state["int_ey"] + Dp * dey

    # ── [4. DEMO CODE: CASCADED VELOCITY PID LOOP] ───────────────────────────
    e_vx = v_cmd_x - vx_meas
    e_vy = v_cmd_y - vy_meas

    # Integrate velocity error with anti-windup clamping [-100, +100]
    state["int_evx"] = max(-100.0, min(100.0, state.get("int_evx", 0.0) + e_vx * dt_c))
    state["int_evy"] = max(-100.0, min(100.0, state.get("int_evy", 0.0) + e_vy * dt_c))

    devx = (e_vx - state.get("prev_evx", e_vx)) / dt_c
    devy = (e_vy - state.get("prev_evy", e_vy)) / dt_c
    state["prev_evx"] = e_vx
    state["prev_evy"] = e_vy

    u_x = Pv * e_vx + Iv * state["int_evx"] + Dv * devx
    u_y = Pv * e_vy + Iv * state["int_evy"] + Dv * devy

    # Convert pixel-space acceleration/torque command to physical motor angular velocity (deg/s)
    pan_rate = u_x / px_per_deg_x
    tilt_rate = u_y / px_per_deg_y

    # ── [5. RETURN CONTRACT] ──────────────────────────────────────────────────
    # OUTPUT EXPLANATION:
    # --------------------------------------------------------------------------
    # Return a dictionary with exact keys "pan_rate" and "tilt_rate":
    #   - "pan_rate"  (float): Gimbal azimuth angular velocity command in deg/s.
    #                          Positive (+) commands gimbal to pan RIGHT.
    #                          Negative (-) commands gimbal to pan LEFT.
    #   - "tilt_rate" (float): Gimbal elevation angular velocity command in deg/s.
    #                          Positive (+) commands gimbal to tilt DOWN.
    #                          Negative (-) commands gimbal to tilt UP.
    # * What the engine does: Clamps rates to [+/- max_rate] and drives physical motors.
    # --------------------------------------------------------------------------
    return {
        "pan_rate": float(pan_rate),
        "tilt_rate": float(tilt_rate),
    }
'''


def validate_vision_output(res: Any) -> bool:
    """Validate that vision plugin output conforms to the vision contract."""
    if res is None:
        return True
    if not isinstance(res, dict):
        return False
    if "x" not in res or "y" not in res:
        return False
    if not isinstance(res["x"], (int, float)) or not isinstance(res["y"], (int, float)):
        return False
    if math.isnan(res["x"]) or math.isnan(res["y"]):
        return False
    return True


def validate_tracking_output(res: Any) -> bool:
    """Validate that tracking plugin output conforms to the tracking contract."""
    if not isinstance(res, dict):
        return False
    for k in ("x", "y", "vx", "vy"):
        if k not in res or not isinstance(res[k], (int, float)) or math.isnan(res[k]):
            return False
    return True


def validate_control_output(res: Any) -> bool:
    """Validate that control plugin output conforms to the control contract."""
    if not isinstance(res, dict):
        return False
    for k in ("pan_rate", "tilt_rate"):
        if k not in res or not isinstance(res[k], (int, float)) or math.isnan(res[k]):
            return False
    return True

