"""
Default NETRA Adapter Functions.
These wrap existing engine pipeline components into the standardized plugin contract signatures.
"""

from typing import Optional, Dict, Any
from ..core.types import Detection, CameraCommand


def default_vision(
    image: Any,
    width: int,
    height: int,
    ctx: Dict[str, Any],
    params: Dict[str, Any],
    *,
    _engine: Any = None,
) -> Optional[Dict[str, Any]]:
    """
    Adapter for NETRA default Vision pipeline.
    Calls Preprocessor + SpotDetector + BeaconVerifierCNN.
    """
    if _engine is None:
        return None

    clean_img, mask, _ = _engine.preprocessor.process(image)
    candidates = _engine.detector.detect(image, mask=mask, intensity_image=clean_img)
    verified = _engine.verifier.verify_detections(image, candidates)

    if not verified:
        return None

    # Apply Mahalanobis gating if track is active
    best_det = _engine.kalman.select_best_detection(verified) if _engine.kalman.is_initialized else verified[0]
    if best_det is None:
        return None

    cand_list = [
        {"x": d.x, "y": d.y, "confidence": d.score, "intensity": d.intensity}
        for d in verified
    ]

    return {
        "x": float(best_det.x),
        "y": float(best_det.y),
        "confidence": float(best_det.score),
        "_candidates": cand_list,
    }


def default_tracking(
    measurement: Optional[Dict[str, Any]],
    dt: float,
    state: Dict[str, Any],
    ctx: Dict[str, Any],
    params: Dict[str, Any],
    *,
    _engine: Any = None,
) -> Dict[str, Any]:
    """
    Adapter for NETRA default Tracking pipeline.
    Calls IMMTracker / KalmanTracker + Optical Flow & Particle Filter handling.
    """
    if _engine is None:
        return {"x": 320.0, "y": 240.0, "vx": 0.0, "vy": 0.0}

    kalman = _engine.kalman
    pred_x, pred_y = kalman.predict()

    # Retrieve flow estimation from engine context or last calculation
    flow_res = getattr(_engine, "_last_flow", None)

    if measurement is not None:
        track = kalman.update(
            measurement["x"],
            measurement["y"],
            score=measurement.get("confidence", 1.0),
            flow=flow_res,
        )
    else:
        track = kalman.coast(flow=flow_res)

    return {
        "x": float(track.x),
        "y": float(track.y),
        "vx": float(track.vx),
        "vy": float(track.vy),
    }


def default_control(
    error: Dict[str, float],
    velocity: Dict[str, float],
    dt: float,
    state: Dict[str, Any],
    ctx: Dict[str, Any],
    params: Dict[str, Any],
    *,
    _engine: Any = None,
) -> Dict[str, float]:
    """
    Adapter for NETRA default Control pipeline.
    Calls PIDController.compute().
    """
    if _engine is None:
        return {"pan_rate": 0.0, "tilt_rate": 0.0}

    ctrl = _engine.controller

    # Convert relative error (from center 320, 240) back to estimated screen coords
    half_w = _engine.cfg.camera.half_w
    half_h = _engine.cfg.camera.half_h
    est_x = error["ex"] + half_w
    est_y = error["ey"] + half_h

    # Update controller camera rate hints for feedforward
    ctrl.set_camera_rates(
        pan_rate_px_s=_engine.camera._pan_rate * _engine.cfg.camera.px_per_deg_x,
        tilt_rate_px_s=_engine.camera._tilt_rate * _engine.cfg.camera.px_per_deg_y,
    )

    fsm_state = ctx.get("fsm_state", "TRACK")
    cmd: CameraCommand = ctrl.compute(
        est_x,
        est_y,
        velocity.get("vx", 0.0),
        velocity.get("vy", 0.0),
        state=fsm_state,
    )

    return {
        "pan_rate": float(cmd.pan_rate_deg_per_s),
        "tilt_rate": float(cmd.tilt_rate_deg_per_s),
    }
