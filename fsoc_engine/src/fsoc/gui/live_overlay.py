"""
src/fsoc/gui/live_overlay.py
============================
High-Performance Tactical HUD & Telemetry Overlay Engine for FSOC Terminals.
Renders mission-control visual overlays on camera viewport frames:
- Target tracking reticle, crosshair, and sub-pixel bounding box
- Tracking state pill (SEARCH / ACQUIRE / TRACK / LOST / REACQUIRE)
- Telemetry readout (Pan/Tilt, Tracking Error, Loop FPS, CNN Confidence)
- Integrated 2000x2000 full-scene radar minimap showing camera FOV rectangle
"""
from __future__ import annotations
from typing import Optional
import cv2
import numpy as np

from ..core.types import TrackState, Detection, Point, ViewportFrame, FrameMetrics


# Theme Color Palette (BGR format for OpenCV)
COLOR_BG_DARK = (15, 20, 25)
COLOR_TEXT = (240, 240, 240)
COLOR_MUTED = (160, 160, 160)
COLOR_CYAN = (255, 220, 0)       # Cyan in BGR
COLOR_GREEN = (80, 220, 60)      # Bright Green
COLOR_RED = (60, 60, 240)        # Bright Red
COLOR_AMBER = (40, 165, 255)     # Amber / Orange
COLOR_PURPLE = (230, 120, 180)   # Purple


class HUDOverlayRenderer:
    """
    Renders professional telemetry and tracking overlays onto frames.
    """
    def __init__(self, res_x: int = 640, res_y: int = 480) -> None:
        self.res_x = res_x
        self.res_y = res_y
        self.cx = res_x // 2
        self.cy = res_y // 2

    def draw_crosshair(
        self, img: np.ndarray, color: tuple[int, int, int] = COLOR_CYAN, gap: int = 12, size: int = 24
    ) -> None:
        """Draw central boresight reticle."""
        # Top
        cv2.line(img, (self.cx, self.cy - gap - size), (self.cx, self.cy - gap), color, 1)
        # Bottom
        cv2.line(img, (self.cx, self.cy + gap), (self.cx, self.cy + gap + size), color, 1)
        # Left
        cv2.line(img, (self.cx - gap - size, self.cy), (self.cx - gap, self.cy), color, 1)
        # Right
        cv2.line(img, (self.cx + gap, self.cy), (self.cx + gap + size, self.cy), color, 1)
        # Small center circle
        cv2.circle(img, (self.cx, self.cy), 2, color, -1)

    def draw_target_box(
        self,
        img: np.ndarray,
        track: TrackState,
        box_radius: int = 16,
        color: tuple[int, int, int] = COLOR_GREEN,
    ) -> None:
        """Draw tactical corner brackets around estimated beacon position."""
        tx, ty = int(round(track.x)), int(round(track.y))
        r = box_radius
        d = 6  # bracket corner length

        # Top-Left
        cv2.line(img, (tx - r, ty - r), (tx - r + d, ty - r), color, 2)
        cv2.line(img, (tx - r, ty - r), (tx - r, ty - r + d), color, 2)
        # Top-Right
        cv2.line(img, (tx + r, ty - r), (tx + r - d, ty - r), color, 2)
        cv2.line(img, (tx + r, ty - r), (tx + r, ty - r + d), color, 2)
        # Bottom-Left
        cv2.line(img, (tx - r, ty + r), (tx - r + d, ty + r), color, 2)
        cv2.line(img, (tx - r, ty + r), (tx - r, ty - r - d), color, 2)
        # Bottom-Right
        cv2.line(img, (tx + r, ty + r), (tx + r - d, ty + r), color, 2)
        cv2.line(img, (tx + r, ty + r), (tx + r, ty + r - d), color, 2)

        # Center dot
        cv2.circle(img, (tx, ty), 2, color, -1)

        # Velocity vector
        vx, vy = int(round(track.vx * 0.15)), int(round(track.vy * 0.15))
        if abs(vx) > 1 or abs(vy) > 1:
            cv2.arrowedLine(img, (tx, ty), (tx + vx, ty + vy), color, 1, tipLength=0.3)

    def draw_state_badge(
        self, img: np.ndarray, state: str, x: int = 15, y: int = 15
    ) -> None:
        """Render glowing state status pill."""
        color_map = {
            "SEARCH": (COLOR_AMBER, (20, 50, 70)),
            "ACQUIRE": (COLOR_CYAN, (20, 60, 60)),
            "TRACK": (COLOR_GREEN, (20, 60, 25)),
            "LOST": (COLOR_RED, (30, 20, 70)),
            "REACQUIRE": (COLOR_PURPLE, (50, 25, 60)),
        }
        fg_col, bg_col = color_map.get(state, (COLOR_MUTED, (30, 30, 30)))

        text = f"MODE: {state}"
        (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        pad = 6
        cv2.rectangle(img, (x, y), (x + w + pad * 2, y + h + pad * 2), bg_col, -1)
        cv2.rectangle(img, (x, y), (x + w + pad * 2, y + h + pad * 2), fg_col, 1)
        cv2.putText(
            img, text, (x + pad, y + h + pad - 1),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, fg_col, 2, cv2.LINE_AA
        )

    def draw_telemetry_sidebar(
        self,
        img: np.ndarray,
        pan_deg: float,
        tilt_deg: float,
        error_px: Optional[float],
        fps: float,
        latency_ms: float,
        confidence: float,
        prob_cv: float = 0.0,
        prob_ct: float = 0.0,
        prob_rw: float = 0.0,
        dominant_model: str = "CV",
    ) -> None:
        """Draw right-hand semi-transparent telemetry data block."""
        x0, y0 = self.res_x - 195, 15
        w_box, h_box = 180, 160

        # Background card
        sub = img[y0:y0 + h_box, x0:x0 + w_box]
        bg = np.full_like(sub, 20)
        cv2.addWeighted(sub, 0.35, bg, 0.65, 0, sub)
        cv2.rectangle(img, (x0, y0), (x0 + w_box, y0 + h_box), (60, 70, 80), 1)

        err_str = f"{error_px:.2f} px" if error_px is not None else "-- px"
        imm_str = f"CV:{prob_cv*100:.0f}% CT:{prob_ct*100:.0f}% RW:{prob_rw*100:.0f}%"

        lines = [
            ("TELEMETRY", COLOR_CYAN, 0.45, 1),
            (f"PAN:  {pan_deg:+6.2f} deg", COLOR_TEXT, 0.38, 1),
            (f"TILT: {tilt_deg:+6.2f} deg", COLOR_TEXT, 0.38, 1),
            (f"ERR:  {err_str}", COLOR_GREEN if (error_px or 0) <= 10.0 else COLOR_RED, 0.38, 1),
            (f"CONF: {confidence * 100:.1f} %", COLOR_TEXT, 0.38, 1),
            (f"FPS:  {fps:5.1f} ({latency_ms:.1f}ms)", COLOR_TEXT, 0.38, 1),
            (f"IMM:  {dominant_model}", COLOR_AMBER if dominant_model == "CT" else (COLOR_PURPLE if dominant_model == "RW" else COLOR_CYAN), 0.38, 1),
            (imm_str, COLOR_MUTED, 0.34, 1),
        ]

        cur_y = y0 + 16
        for text, col, scale, thick in lines:
            cv2.putText(img, text, (x0 + 8, cur_y), cv2.FONT_HERSHEY_SIMPLEX, scale, col, thick, cv2.LINE_AA)
            cur_y += 18

    def draw_minimap(
        self,
        img: np.ndarray,
        cam_cx: float,
        cam_cy: float,
        target_pt: Optional[Point],
        scene_w: int = 2000,
        scene_h: int = 2000,
        map_size: int = 110,
    ) -> None:
        """
        Draw 2000x2000 scene radar minimap in bottom-left corner.
        Shows full scene, target beacon, and camera FOV crop box.
        """
        x0, y0 = 15, self.res_y - map_size - 15

        # Minimap background
        sub = img[y0:y0 + map_size, x0:x0 + map_size]
        bg = np.full_like(sub, 15)
        cv2.addWeighted(sub, 0.2, bg, 0.8, 0, sub)
        cv2.rectangle(img, (x0, y0), (x0 + map_size, y0 + map_size), (70, 80, 90), 1)

        scale = map_size / float(scene_w)

        # Draw camera FOV box
        cam_box_w = int(self.res_x * scale)
        cam_box_h = int(self.res_y * scale)
        cam_x_min = x0 + int((cam_cx - self.res_x / 2.0) * scale)
        cam_y_min = y0 + int((cam_cy - self.res_y / 2.0) * scale)
        cv2.rectangle(
            img,
            (cam_x_min, cam_y_min),
            (cam_x_min + cam_box_w, cam_y_min + cam_box_h),
            COLOR_CYAN,
            1,
        )

        # Draw target spot on minimap
        if target_pt is not None:
            tgt_mx = x0 + int(target_pt.x * scale)
            tgt_my = y0 + int(target_pt.y * scale)
            cv2.circle(img, (tgt_mx, tgt_my), 2, COLOR_GREEN, -1)

        cv2.putText(
            img, "RADAR", (x0 + 4, y0 + 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.35, COLOR_MUTED, 1, cv2.LINE_AA
        )

    def render_hud(
        self,
        frame_img: np.ndarray,
        metrics: FrameMetrics,
        track_state: Optional[TrackState] = None,
        cam_cx: float = 1000.0,
        cam_cy: float = 1000.0,
        target_scene_pt: Optional[Point] = None,
    ) -> np.ndarray:
        """
        Composite all tactical HUD elements onto the given image.
        Returns a 3-channel BGR image ready for display.
        """
        # Ensure 3-channel BGR
        if frame_img.ndim == 2:
            display_img = cv2.cvtColor(frame_img, cv2.COLOR_GRAY2BGR)
        else:
            display_img = frame_img.copy()

        # 1. Central boresight crosshairs
        self.draw_crosshair(display_img)

        # 2. Tracking reticle if track exists
        if track_state is not None and track_state.locked:
            self.draw_target_box(display_img, track_state)

        # 3. Status Badge
        self.draw_state_badge(display_img, metrics.state)

        # 4. Telemetry sidebar
        fps = 1000.0 / max(0.1, metrics.proc_ms)
        self.draw_telemetry_sidebar(
            display_img,
            pan_deg=metrics.pan_deg,
            tilt_deg=metrics.tilt_deg,
            error_px=metrics.error_px,
            fps=fps,
            latency_ms=metrics.proc_ms,
            confidence=metrics.confidence,
            prob_cv=metrics.prob_cv,
            prob_ct=metrics.prob_ct,
            prob_rw=metrics.prob_rw,
            dominant_model=metrics.dominant_model,
        )

        # 5. Radar Minimap
        self.draw_minimap(
            display_img,
            cam_cx=cam_cx,
            cam_cy=cam_cy,
            target_pt=target_scene_pt,
        )

        # 6. Custom Plugin HUD Banner
        self.draw_plugin_banner(display_img)

        return display_img

    def draw_plugin_banner(self, img: np.ndarray) -> None:
        """Draw top banner showing active custom algorithm plugins."""
        from ..plugins.registry import registry, SLOTS
        active_customs = [f"{s.upper()}: {registry.get_label(s)}" for s in SLOTS if registry.is_custom(s)]
        if not active_customs:
            return
        text = "⚡ CUSTOM: " + " | ".join(active_customs)
        h, w = img.shape[:2]
        cv2.rectangle(img, (0, 0), (w, 22), (40, 20, 0), -1)
        cv2.putText(img, text, (8, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1, cv2.LINE_AA)
