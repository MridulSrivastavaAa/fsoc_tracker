"""
src/fsoc/core/camera.py
========================
VirtualCamera: implements the pan-tilt actuator model and viewport crop.

Key maths (from PS spec):
  Angular scale:  640 px / 4° = 160 px/degree  (same for Y: 480/3 = 160 px/deg)
  Viewport centre (cx, cy) in screen pixels determines the crop.
  Pan/tilt state stored in degrees; pixels are derived quantities.

Physical actuator model:
  - Rate command is clipped to max_pan/tilt_deg_per_s.
  - Acceleration is clipped to max_accel_deg_per_s2.
  - A fixed latency_frames=1 delay: command at frame k takes effect at frame k+1.
"""
from __future__ import annotations
import numpy as np
from .config import CameraConfig
from .types import CameraCommand, ViewportFrame, FullFrame, Point


class VirtualCamera:
    """
    Stateful virtual pan-tilt camera.

    State: (pan_deg, tilt_deg)  →  (cx_px, cy_px) viewport centre.
    Public API:
      render(full_frame)         →  ViewportFrame
      apply_command(cmd, dt)     →  updates internal state
      screen_to_viewport(x, y)  →  viewport pixel coords
      viewport_to_screen(x, y)  →  screen pixel coords
    """

    def __init__(self, cfg: CameraConfig, scene_w: int, scene_h: int) -> None:
        self.cfg = cfg
        self.scene_w = scene_w
        self.scene_h = scene_h

        # Derived angular scale (px/deg), same on both axes
        self._scale_x = cfg.px_per_deg_x   # = res_x / fov_x_deg
        self._scale_y = cfg.px_per_deg_y   # = res_y / fov_y_deg

        # Initial viewport centre
        init_cx = cfg.initial_cx if cfg.initial_cx is not None else scene_w / 2.0
        init_cy = cfg.initial_cy if cfg.initial_cy is not None else scene_h / 2.0

        # Pan/tilt are measured from the scene centre
        self._cx = float(init_cx)
        self._cy = float(init_cy)

        # Current actual rates (for acceleration limiting)
        self._pan_rate: float = 0.0    # deg/s
        self._tilt_rate: float = 0.0   # deg/s

        # Command queue for latency simulation
        # Each entry is (pan_rate_cmd, tilt_rate_cmd)
        self._cmd_queue: list[tuple[float, float]] = [(0.0, 0.0)] * cfg.latency_frames

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cx(self) -> float:
        """Current viewport centre x in screen pixels."""
        return self._cx

    @property
    def cy(self) -> float:
        """Current viewport centre y in screen pixels."""
        return self._cy

    @property
    def pan_deg(self) -> float:
        """Pan angle in degrees (0 = screen centre)."""
        return (self._cx - self.scene_w / 2.0) / self._scale_x

    @property
    def tilt_deg(self) -> float:
        """Tilt angle in degrees (0 = screen centre, positive = down)."""
        return (self._cy - self.scene_h / 2.0) / self._scale_y

    # ------------------------------------------------------------------
    # Command application (called once per simulation step)
    # ------------------------------------------------------------------

    def apply_command(self, cmd: CameraCommand, dt: float) -> None:
        """
        Push cmd into the latency queue; apply the oldest command.
        Updates viewport centre (cx, cy) with physical constraints.
        """
        # Enqueue new command
        self._cmd_queue.append((cmd.pan_rate_deg_per_s, cmd.tilt_rate_deg_per_s))

        # Dequeue the oldest command (after latency_frames delay)
        pan_cmd, tilt_cmd = self._cmd_queue.pop(0)

        # Clip rate to physical max
        pan_cmd = float(np.clip(pan_cmd,
                                -self.cfg.max_pan_deg_per_s,
                                self.cfg.max_pan_deg_per_s))
        tilt_cmd = float(np.clip(tilt_cmd,
                                 -self.cfg.max_tilt_deg_per_s,
                                 self.cfg.max_tilt_deg_per_s))

        # Acceleration limit (rate of change of rate)
        max_delta_rate = self.cfg.max_accel_deg_per_s2 * dt
        self._pan_rate += float(np.clip(pan_cmd - self._pan_rate,
                                        -max_delta_rate, max_delta_rate))
        self._tilt_rate += float(np.clip(tilt_cmd - self._tilt_rate,
                                         -max_delta_rate, max_delta_rate))

        # Integrate rate to position (in screen pixels)
        self._cx += self._pan_rate * self._scale_x * dt
        self._cy += self._tilt_rate * self._scale_y * dt

        # Clamp viewport centre so the full crop stays on the scene
        half_w = self.cfg.half_w
        half_h = self.cfg.half_h
        self._cx = float(np.clip(self._cx, half_w, self.scene_w - half_w))
        self._cy = float(np.clip(self._cy, half_h, self.scene_h - half_h))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, full_frame: FullFrame) -> ViewportFrame:
        """
        Crop the 640x480 viewport from the full-scene image.
        Also maps ground-truth beacon positions into viewport coordinates.
        """
        img = full_frame.image
        half_w = int(self.cfg.half_w)
        half_h = int(self.cfg.half_h)

        # Integer pixel boundaries
        x1 = int(round(self._cx)) - half_w
        y1 = int(round(self._cy)) - half_h
        x2 = x1 + self.cfg.res_x
        y2 = y1 + self.cfg.res_y

        # Crop (boundaries already guaranteed valid by apply_command clamp)
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(self.scene_w, x2)
        y2 = min(self.scene_h, y2)
        crop = img[y1:y2, x1:x2]

        # Pad to exactly (res_y, res_x) if any edge clipping occurred
        viewport_img = np.zeros((self.cfg.res_y, self.cfg.res_x), dtype=np.uint8)
        paste_h = min(crop.shape[0], self.cfg.res_y)
        paste_w = min(crop.shape[1], self.cfg.res_x)
        viewport_img[:paste_h, :paste_w] = crop[:paste_h, :paste_w]

        # Map GT from screen → viewport coords
        gt_vp: list[Point] | None = None
        if full_frame.ground_truth is not None:
            gt_vp = []
            for pt in full_frame.ground_truth:
                vx, vy = self.screen_to_viewport(pt.x, pt.y)
                gt_vp.append(Point(vx, vy))

        return ViewportFrame(
            image=viewport_img,
            frame_index=full_frame.frame_index,
            timestamp_s=full_frame.timestamp_s,
            pan_deg=self.pan_deg,
            tilt_deg=self.tilt_deg,
            cx_px=self._cx,
            cy_px=self._cy,
            ground_truth_viewport=gt_vp,
        )

    # ------------------------------------------------------------------
    # Coordinate transforms
    # ------------------------------------------------------------------

    def screen_to_viewport(self, sx: float, sy: float) -> tuple[float, float]:
        """Convert screen-coordinate point to viewport-coordinate point."""
        half_w = self.cfg.half_w
        half_h = self.cfg.half_h
        vx = sx - (self._cx - half_w)
        vy = sy - (self._cy - half_h)
        return vx, vy

    def viewport_to_screen(self, vx: float, vy: float) -> tuple[float, float]:
        """Convert viewport-coordinate point to screen-coordinate point."""
        half_w = self.cfg.half_w
        half_h = self.cfg.half_h
        sx = vx + (self._cx - half_w)
        sy = vy + (self._cy - half_h)
        return sx, sy

    def is_in_viewport(self, sx: float, sy: float) -> bool:
        """Return True if screen-coordinate point (sx, sy) is inside the viewport."""
        vx, vy = self.screen_to_viewport(sx, sy)
        return (0 <= vx < self.cfg.res_x) and (0 <= vy < self.cfg.res_y)
