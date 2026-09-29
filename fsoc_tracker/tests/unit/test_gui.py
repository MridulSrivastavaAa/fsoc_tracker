"""
tests/unit/test_gui.py
======================
Unit & Integration Tests for Phase 6: Desktop GUI & HUD Overlay Engine.
Validates:
1. HUDOverlayRenderer reticle, bounding box, state badge, telemetry, and minimap
2. GUI application instantiation and headless single-step update
"""
import pytest
import numpy as np
import cv2

from fsoc.core.types import TrackState, FrameMetrics, Point
from fsoc.gui.live_overlay import HUDOverlayRenderer


# ===========================================================================
# 1. HUD Overlay Engine Tests
# ===========================================================================

class TestHUDOverlayRenderer:
    def test_output_shape_and_channels(self) -> None:
        renderer = HUDOverlayRenderer(res_x=640, res_y=480)
        raw_gray = np.full((480, 640), 30, dtype=np.uint8)

        metric = FrameMetrics(
            frame_index=0,
            timestamp_s=0.0,
            state="TRACK",
            error_px=2.5,
            proc_ms=8.0,
            pan_deg=1.2,
            tilt_deg=-0.8,
        )
        track = TrackState(x=320.0, y=240.0, vx=10.0, vy=5.0, confidence=0.9, locked=True)

        hud_bgr = renderer.render_hud(
            raw_gray,
            metrics=metric,
            track_state=track,
            cam_cx=1000.0,
            cam_cy=1000.0,
            target_scene_pt=Point(1000.0, 1000.0),
        )

        assert hud_bgr.shape == (480, 640, 3)
        assert hud_bgr.dtype == np.uint8

    def test_crosshair_modifies_center_pixels(self) -> None:
        renderer = HUDOverlayRenderer(res_x=640, res_y=480)
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        renderer.draw_crosshair(img)

        # Center dot should be drawn at (320, 240)
        assert np.any(img[240, 320] > 0)

    def test_target_box_drawn_around_track(self) -> None:
        renderer = HUDOverlayRenderer(res_x=640, res_y=480)
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        track = TrackState(x=200.0, y=150.0, vx=0.0, vy=0.0, confidence=0.85, locked=True)

        renderer.draw_target_box(img, track, box_radius=16)
        # Center dot at (200, 150)
        assert np.any(img[150, 200] > 0)
        # Corner bracket at (200 - 16, 150 - 16) = (184, 134)
        assert np.any(img[134, 184] > 0)

    def test_state_badge_all_modes(self) -> None:
        renderer = HUDOverlayRenderer(res_x=640, res_y=480)
        states = ["SEARCH", "ACQUIRE", "TRACK", "LOST", "REACQUIRE"]

        for s in states:
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            renderer.draw_state_badge(img, state=s)
            # Verify top-left region is drawn
            assert np.any(img[15:40, 15:100] > 0)

    def test_minimap_renders_radar(self) -> None:
        renderer = HUDOverlayRenderer(res_x=640, res_y=480)
        img = np.zeros((480, 640, 3), dtype=np.uint8)

        renderer.draw_minimap(
            img,
            cam_cx=1200.0,
            cam_cy=800.0,
            target_pt=Point(1150.0, 850.0),
            scene_w=2000,
            scene_h=2000,
        )

        # Bottom-left minimap region (y around 355 to 465, x around 15 to 125)
        assert np.any(img[355:465, 15:125] > 0)


# ===========================================================================
# 2. GUI App Headless Instantiation Tests
# ===========================================================================

class TestGUIApp:
    def test_gui_app_initialization(self) -> None:
        """Verify GUI app constructs safely without throwing exceptions."""
        try:
            import tkinter as tk
            from fsoc.gui.app import FSOCTrackerApp

            root = tk.Tk()
            root.withdraw()  # Headless mode for automated tests

            app = FSOCTrackerApp(root)
            assert app.root is not None
            assert app.engine is not None

            # Test single step in headless mode
            app.step_frame()
            assert len(app.engine.metrics_history) == 1

            # Test reset
            app.reset_system()
            assert len(app.engine.metrics_history) == 0

            root.destroy()
        except tk.TclError:
            pytest.skip("No graphical display available in current environment")
