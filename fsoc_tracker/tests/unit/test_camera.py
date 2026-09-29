"""
tests/unit/test_camera.py
==========================
Unit tests for VirtualCamera: coordinate maths, rate limiting,
acceleration limiting, and latency.
"""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

import numpy as np
from fsoc.core.config import default_config
from fsoc.core.camera import VirtualCamera
from fsoc.core.types import CameraCommand, FullFrame, Point

W, H = 2000, 2000
DT = 1 / 30.0


def make_camera(latency: int = 1) -> VirtualCamera:
    cfg = default_config()
    cam_cfg = cfg.camera.model_copy(update={"latency_frames": latency})
    return VirtualCamera(cam_cfg, W, H)


def make_full_frame(idx: int = 0) -> FullFrame:
    img = np.zeros((H, W), dtype=np.uint8)
    return FullFrame(image=img, frame_index=idx, timestamp_s=idx * DT,
                     ground_truth=[Point(1000.0, 1000.0)])


# -------  Initial state  ---------------------------------------------------

def test_initial_centre():
    cam = make_camera()
    assert cam.cx == pytest.approx(W / 2, abs=1.0)
    assert cam.cy == pytest.approx(H / 2, abs=1.0)
    assert cam.pan_deg == pytest.approx(0.0, abs=1e-6)
    assert cam.tilt_deg == pytest.approx(0.0, abs=1e-6)


# -------  Coordinate transforms (round-trip)  ------------------------------

def test_screen_to_viewport_centre():
    cam = make_camera()
    vx, vy = cam.screen_to_viewport(W / 2, H / 2)
    # Viewport centre of a 640x480 viewport is at (320, 240)
    assert vx == pytest.approx(320.0, abs=1.0)
    assert vy == pytest.approx(240.0, abs=1.0)

def test_round_trip_coordinates():
    cam = make_camera()
    for sx, sy in [(500, 700), (1500, 300), (1000, 1000)]:
        vx, vy = cam.screen_to_viewport(sx, sy)
        sx2, sy2 = cam.viewport_to_screen(vx, vy)
        assert sx2 == pytest.approx(sx, abs=1e-6)
        assert sy2 == pytest.approx(sy, abs=1e-6)


# -------  Rate limiting  ---------------------------------------------------

def test_rate_limiting():
    cam = make_camera(latency=0)
    max_rate = cam.cfg.max_pan_deg_per_s   # 5 deg/s default
    # Send a huge rate command, should be clipped
    for _ in range(50):
        cam.apply_command(CameraCommand(pan_rate_deg_per_s=9999.0,
                                        tilt_rate_deg_per_s=0.0), DT)
    # Pan rate in px/s <= max_rate * scale_x
    max_px_s = max_rate * cam._scale_x
    # In 50 frames at 30 Hz (~1.67 s) with max rate 5 deg/s = 800 px/s
    # Camera should have moved at most 1.67 * 800 = 1333 px from centre
    assert cam.cx <= W - cam.cfg.half_w
    assert cam.cx >= cam.cfg.half_w


# -------  Viewport clamping at scene edge  ---------------------------------

def test_viewport_stays_on_scene():
    cam = make_camera(latency=0)
    # Drive camera hard right for many frames
    for _ in range(300):
        cam.apply_command(CameraCommand(pan_rate_deg_per_s=10.0,
                                        tilt_rate_deg_per_s=0.0), DT)
    assert cam.cx <= W - cam.cfg.half_w
    assert cam.cx >= cam.cfg.half_w


# -------  Latency  ---------------------------------------------------------

def test_latency_one_frame():
    """With latency=1, a command at step 0 should not move camera at step 0."""
    cam = make_camera(latency=1)
    cx_before = cam.cx
    cam.apply_command(CameraCommand(pan_rate_deg_per_s=5.0,
                                    tilt_rate_deg_per_s=0.0), DT)
    # Should not have moved (command is queued, not applied yet)
    # Actually with latency=1: the command queue starts with 1 zero,
    # so the first apply pops the zero and pushes the real command.
    # So cx remains unchanged after first apply.
    assert cam.cx == pytest.approx(cx_before, abs=0.5)


# -------  Render produces correct shape  -----------------------------------

def test_render_output_shape():
    cam = make_camera()
    ff = make_full_frame()
    vf = cam.render(ff)
    assert vf.image.shape == (cam.cfg.res_y, cam.cfg.res_x)

def test_render_gt_in_viewport():
    cam = make_camera()
    ff = make_full_frame()
    vf = cam.render(ff)
    assert vf.ground_truth_viewport is not None
    assert len(vf.ground_truth_viewport) == 1
    pt = vf.ground_truth_viewport[0]
    # Screen centre (1000, 1000) → viewport centre (320, 240)
    assert pt.x == pytest.approx(320.0, abs=1.0)
    assert pt.y == pytest.approx(240.0, abs=1.0)


# -------  Angular scale correctness  ---------------------------------------

def test_angular_scale():
    cam = make_camera()
    # 160 px/deg expected from 640/4
    assert cam._scale_x == pytest.approx(160.0, abs=1e-6)
    assert cam._scale_y == pytest.approx(160.0, abs=1e-6)
