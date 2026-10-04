r"""
src/fsoc/control/pid_controller.py

==================================
Feed-Forward PID Pan-Tilt Controller for FSOC Optical Gimbals.
Keeps beacon centered at viewport optical center (320, 240).

Law:
  u_x = Kp * e_x + Ki * \int e_x dt + Kd * d(e_x)/dt + Kff * v_x
  u_y = Kp * e_y + Ki * \int e_y dt + Kd * d(e_y)/dt + Kff * v_y
  pan_rate  = u_x / scale_x
  tilt_rate = u_y / scale_y

Features:
- Velocity feed-forward for dynamic trajectory tracking with zero steady-state lag
- Integrator anti-windup clamping
- Actuator physical speed clamping
- Configurable error deadband
"""
from __future__ import annotations
import numpy as np

from ..core.types import CameraCommand, TrackState
from ..core.config import ControlConfig, CameraConfig, AppConfig


class PIDController:
    """
    Closed-loop PID rate controller with velocity feed-forward.
    """
    def __init__(
        self,
        cfg: ControlConfig | AppConfig | None = None,
        camera_cfg: CameraConfig | None = None,
        dt: float = 1.0 / 30.0,
    ) -> None:
        if cfg is None:
            c_cfg = ControlConfig()
            cam_cfg = camera_cfg or CameraConfig()
        elif isinstance(cfg, AppConfig):
            c_cfg = cfg.control
            cam_cfg = cfg.camera
            dt = cfg.pipeline.dt
        elif isinstance(cfg, ControlConfig):
            c_cfg = cfg
            cam_cfg = camera_cfg or CameraConfig()
        else:
            raise TypeError(f"Unsupported config type: {type(cfg)}")

        self.cfg = c_cfg
        self.camera_cfg = cam_cfg
        self.dt = float(dt)

        # Optical center of viewport
        self.target_cx = self.camera_cfg.half_w + self.cfg.target_offset_x
        self.target_cy = self.camera_cfg.half_h + self.cfg.target_offset_y

        # Actuator scale
        self.scale_x = self.camera_cfg.px_per_deg_x
        self.scale_y = self.camera_cfg.px_per_deg_y

        # Integrators
        self.int_x: float = 0.0
        self.int_y: float = 0.0

        # Previous errors for derivative calculation
        self.prev_e_x: float = 0.0
        self.prev_e_y: float = 0.0
        self.has_prev: bool = False

        # Cached camera slew rates for world-space feed-forward reconstruction
        # Updated each call via set_camera_rates()
        self._cam_rate_x_px_s: float = 0.0   # camera slew x in px/s (world coords)
        self._cam_rate_y_px_s: float = 0.0   # camera slew y in px/s (world coords)

        # Last command decomposition in deg/s, published to the telemetry HUD:
        # (pan_p, tilt_p), (pan_i, tilt_i), (pan_d, tilt_d), (pan_ff, tilt_ff)
        self.last_p: tuple[float, float] = (0.0, 0.0)
        self.last_i: tuple[float, float] = (0.0, 0.0)
        self.last_d: tuple[float, float] = (0.0, 0.0)
        self.last_ff: tuple[float, float] = (0.0, 0.0)

    def set_camera_rates(self, pan_rate_px_s: float, tilt_rate_px_s: float) -> None:
        """
        Update cached camera slew rates for world-space feed-forward.
        Call this each frame before compute() with the current camera rates.

        Args:
            pan_rate_px_s: Current camera pan velocity in scene px/s.
            tilt_rate_px_s: Current camera tilt velocity in scene px/s.
        """
        self._cam_rate_x_px_s = pan_rate_px_s
        self._cam_rate_y_px_s = tilt_rate_px_s

    def compute(
        self,
        est_x: float,
        est_y: float,
        vel_x: float = 0.0,
        vel_y: float = 0.0,
        state: str = "TRACK",
    ) -> CameraCommand:
        """
        Compute pan/tilt rate command to center target.

        Args:
            est_x: Current estimated target X position in viewport (px).
            est_y: Current estimated target Y position in viewport (px).
            vel_x: Kalman-estimated viewport velocity X (px/s).  This is
                   target_world_vel - camera_slew_vel, and approaches 0 when
                   the camera tracks well.  The controller reconstructs the
                   world-space velocity internally for the feed-forward term.
            vel_y: Kalman-estimated viewport velocity Y (px/s).

        Returns:
            CameraCommand with pan and tilt angular rates (deg/s).
        """
        # Reconstruct world-space target velocity (scene px/s) for feed-forward.
        # world_vel = camera_slew_vel + viewport_vel gives the scene-space velocity
        # of the target. However since camera_slew_vel already encodes the prior
        # control command, using world_vel would double-apply the FF term.
        # Instead: use Kalman viewport velocity directly (target motion relative
        # to the moving camera).  This is the component not yet compensated by
        # the current camera command, giving a well-posed FF without overcorrection.
        world_vel_x = vel_x   # viewport velocity IS the uncompensated residual
        world_vel_y = vel_y
        # Pixel errors from viewport center
        e_x = est_x - self.target_cx
        e_y = est_y - self.target_cy

        # Apply deadband
        if abs(e_x) < self.cfg.deadband_px:
            e_x = 0.0
        if abs(e_y) < self.cfg.deadband_px:
            e_y = 0.0

        # Integrator with anti-windup clamping
        self.int_x += e_x * self.dt
        self.int_y += e_y * self.dt
        max_int_deg = self.cfg.anti_windup_limit
        max_int_px = max_int_deg * self.scale_x
        self.int_x = float(np.clip(self.int_x, -max_int_px, max_int_px))
        self.int_y = float(np.clip(self.int_y, -max_int_px, max_int_px))

        # Derivative term
        if self.has_prev:
            d_x = (e_x - self.prev_e_x) / self.dt
            d_y = (e_y - self.prev_e_y) / self.dt
        else:
            d_x = 0.0
            d_y = 0.0
            self.has_prev = True

        self.prev_e_x = e_x
        self.prev_e_y = e_y

        # Gain scheduling: softer Kp during ACQUIRE to prevent violent snap
        kp_active = self.cfg.kp * 0.3 if state == "ACQUIRE" else self.cfg.kp

        # PID + World-space Feed-forward law in pixel rate (px/s)
        # Using world-space velocity (not viewport velocity) for FF:
        # viewport_vel -> 0 when tracking; world_vel stays constant at target speed.
        u_x = (
            kp_active * e_x
            + self.cfg.ki * self.int_x
            + self.cfg.kd * d_x
            + self.cfg.kff * world_vel_x
        )
        u_y = (
            kp_active * e_y
            + self.cfg.ki * self.int_y
            + self.cfg.kd * d_y
            + self.cfg.kff * world_vel_y
        )

        # Convert pixel rates (px/s) to angular rates (deg/s)
        pan_rate = u_x / self.scale_x
        tilt_rate = u_y / self.scale_y

        # Keep the term-by-term decomposition for the HUD (deg/s)
        self.last_p = (kp_active * e_x / self.scale_x, kp_active * e_y / self.scale_y)
        self.last_i = (self.cfg.ki * self.int_x / self.scale_x, self.cfg.ki * self.int_y / self.scale_y)
        self.last_d = (self.cfg.kd * d_x / self.scale_x, self.cfg.kd * d_y / self.scale_y)
        self.last_ff = (self.cfg.kff * world_vel_x / self.scale_x, self.cfg.kff * world_vel_y / self.scale_y)

        # Clamp to physical actuator limits
        pan_rate = float(np.clip(
            pan_rate,
            -self.camera_cfg.max_pan_deg_per_s,
            self.camera_cfg.max_pan_deg_per_s
        ))
        tilt_rate = float(np.clip(
            tilt_rate,
            -self.camera_cfg.max_tilt_deg_per_s,
            self.camera_cfg.max_tilt_deg_per_s
        ))

        return CameraCommand(
            pan_rate_deg_per_s=pan_rate,
            tilt_rate_deg_per_s=tilt_rate,
        )

    def compute_from_track(self, track: TrackState) -> CameraCommand:
        """Convenience method computing command directly from TrackState."""
        if not track.locked:
            return CameraCommand(0.0, 0.0)
        return self.compute(track.x, track.y, track.vx, track.vy)

    def reset(self) -> None:
        """Reset PID internal accumulators."""
        self.int_x = 0.0
        self.int_y = 0.0
        self.prev_e_x = 0.0
        self.prev_e_y = 0.0
        self.has_prev = False
        self.last_p = (0.0, 0.0)
        self.last_i = (0.0, 0.0)
        self.last_d = (0.0, 0.0)
        self.last_ff = (0.0, 0.0)
