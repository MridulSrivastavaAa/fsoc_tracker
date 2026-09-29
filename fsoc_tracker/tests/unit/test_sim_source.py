"""
tests/unit/test_sim_source.py
==============================
Integration smoke-test for the full simulation source pipeline:
  Config -> SimulatedSource -> FullFrame (with GT) -> VirtualCamera -> ViewportFrame
"""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

import numpy as np
from fsoc.core.config import default_config, load_config
from fsoc.core.camera import VirtualCamera
from fsoc.core.types import CameraCommand
from fsoc.simulation.sim_source import SimulatedSource

CONFIGS_DIR = pathlib.Path(__file__).parent.parent.parent / "configs"


def test_sim_source_returns_full_frame():
    cfg = default_config()
    src = SimulatedSource(cfg)
    ff = src.next_frame()
    assert ff is not None
    assert ff.image.shape == (cfg.scene.height, cfg.scene.width)
    assert ff.image.dtype == np.uint8
    assert ff.frame_index == 0
    assert ff.ground_truth is not None
    assert len(ff.ground_truth) == 1


def test_sim_source_frame_counter():
    cfg = default_config()
    src = SimulatedSource(cfg)
    for i in range(10):
        ff = src.next_frame()
        assert ff is not None
        assert ff.frame_index == i


def test_sim_source_deterministic():
    """Same seed must produce identical frames."""
    cfg = default_config()
    src1 = SimulatedSource(cfg, seed=123)
    src2 = SimulatedSource(cfg, seed=123)
    for _ in range(5):
        f1 = src1.next_frame()
        f2 = src2.next_frame()
        assert np.array_equal(f1.image, f2.image)
        assert f1.ground_truth[0].x == pytest.approx(f2.ground_truth[0].x)


def test_sim_source_gt_changes_across_frames():
    """Beacon position must move between frames (not stuck)."""
    cfg = default_config()
    src = SimulatedSource(cfg, seed=0)
    positions = []
    for _ in range(30):
        ff = src.next_frame()
        positions.append((ff.ground_truth[0].x, ff.ground_truth[0].y))
    xs = [p[0] for p in positions]
    # At least some movement expected
    assert max(xs) - min(xs) > 0.1


def test_sim_source_stops_after_duration():
    """Source must return None after duration_s * fps frames."""
    cfg = default_config()
    cfg = cfg.model_copy(update={
        "pipeline": cfg.pipeline.model_copy(update={"duration_s": 1.0, "fps": 10.0})
    })
    src = SimulatedSource(cfg)
    frames = []
    while True:
        ff = src.next_frame()
        if ff is None:
            break
        frames.append(ff)
    assert len(frames) == 10  # 1.0 s * 10 fps


def test_sim_source_reset():
    cfg = default_config()
    src = SimulatedSource(cfg, seed=5)
    ff1 = src.next_frame()
    src.next_frame()
    src.reset()
    ff1r = src.next_frame()
    assert np.array_equal(ff1.image, ff1r.image)


def test_full_pipeline_sim_to_viewport():
    """
    Full pipeline smoke test:
    Config → SimulatedSource → FullFrame → VirtualCamera.render() → ViewportFrame
    """
    cfg = default_config()
    src = SimulatedSource(cfg, seed=42)
    cam = VirtualCamera(cfg.camera, cfg.scene.width, cfg.scene.height)

    for step in range(30):
        ff = src.next_frame()
        assert ff is not None

        vf = cam.render(ff)
        assert vf.image.shape == (cfg.camera.res_y, cfg.camera.res_x)
        assert vf.image.dtype == np.uint8
        assert vf.ground_truth_viewport is not None

        # Beacon should be visible in viewport (camera starts at screen centre,
        # so beacon starts near centre too)
        gt = vf.ground_truth_viewport[0]
        # Just check it's a valid Point with finite coords
        assert not (gt.x != gt.x)   # not NaN
        assert not (gt.y != gt.y)

        # Apply idle command (camera stays centred)
        cam.apply_command(CameraCommand(), ff.timestamp_s)


def test_load_config_yaml():
    yaml_file = CONFIGS_DIR / "default.yaml"
    if not yaml_file.exists():
        pytest.skip("default.yaml not found")
    cfg = load_config(yaml_file)
    assert cfg.scene.width == 2000
    assert cfg.camera.res_x == 640
    assert cfg.camera.fov_x_deg == pytest.approx(4.0)
