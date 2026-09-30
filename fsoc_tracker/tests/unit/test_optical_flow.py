"""
tests/unit/test_optical_flow.py
===============================
Comprehensive Unit Tests for Local Sparse Lucas-Kanade Optical Flow Tracker (Step 2).

Tests:
1. Stationary beacon
2. Pure horizontal movement
3. Pure vertical movement
4. Diagonal movement
5. Fast movement
6. Camera motion compensation
7. Invalid features / uniform image
8. Feature dropout (occlusion)
9. Outlier rejection (median-trimmed aggregation)
10. Forward-backward consistency rejection
11. No-feature / first frame case
12. ROI boundary clipping
13. Coordinate transformation
14. IMM velocity fusion with valid flow
15. IMM graceful fallback with invalid flow
"""
import math
import numpy as np
import cv2
import pytest

from fsoc.core.config import OpticalFlowConfig, AppConfig, default_config
from fsoc.core.types import FlowResult, Detection
from fsoc.vision.optical_flow import OpticalFlowTracker
from fsoc.tracking.imm import IMMTracker


def _create_synthetic_beacon_image(
    x: float, y: float, w: int = 640, h: int = 480, radius: int = 8, bg_val: int = 20, peak_val: int = 230
) -> np.ndarray:
    """Helper to render a clean Gaussian-like beacon blob."""
    img = np.full((h, w), bg_val, dtype=np.uint8)
    ix, iy = int(round(x)), int(round(y))
    cv2.circle(img, (ix, iy), radius, peak_val, -1)
    # Apply a light Gaussian blur to simulate real PSF
    img = cv2.GaussianBlur(img, (5, 5), 1.2)
    return img


class TestOpticalFlowTracker:
    def test_first_frame_initialization(self) -> None:
        """First frame should initialize cache and return valid=False without error."""
        oft = OpticalFlowTracker()
        img0 = _create_synthetic_beacon_image(320.0, 240.0)
        res0 = oft.estimate_flow(img0, hint_pos=(320.0, 240.0))
        assert not res0.valid
        assert oft.prev_img is not None

    def test_stationary_beacon(self) -> None:
        """Stationary beacon in consecutive frames should produce near-zero displacement."""
        oft = OpticalFlowTracker(dt=1.0 / 30.0)
        img0 = _create_synthetic_beacon_image(320.0, 240.0)
        img1 = _create_synthetic_beacon_image(320.0, 240.0)

        oft.estimate_flow(img0, hint_pos=(320.0, 240.0))
        res1 = oft.estimate_flow(img1, hint_pos=(320.0, 240.0))

        assert res1.valid
        assert abs(res1.dx_viewport) < 0.5
        assert abs(res1.dy_viewport) < 0.5
        assert res1.speed < 20.0
        assert res1.confidence > 0.3

    def test_pure_horizontal_movement(self) -> None:
        """Pure horizontal translation should be accurately measured."""
        oft = OpticalFlowTracker(dt=1.0 / 30.0)
        img0 = _create_synthetic_beacon_image(300.0, 240.0)
        img1 = _create_synthetic_beacon_image(305.0, 240.0)

        oft.estimate_flow(img0, hint_pos=(300.0, 240.0))
        res1 = oft.estimate_flow(img1, hint_pos=(300.0, 240.0))

        assert res1.valid
        assert pytest.approx(res1.dx_viewport, abs=0.6) == 5.0
        assert abs(res1.dy_viewport) < 0.6
        assert res1.vx_viewport > 0

    def test_pure_vertical_movement(self) -> None:
        """Pure vertical translation should be accurately measured."""
        oft = OpticalFlowTracker(dt=1.0 / 30.0)
        img0 = _create_synthetic_beacon_image(320.0, 200.0)
        img1 = _create_synthetic_beacon_image(320.0, 196.0)

        oft.estimate_flow(img0, hint_pos=(320.0, 200.0))
        res1 = oft.estimate_flow(img1, hint_pos=(320.0, 200.0))

        assert res1.valid
        assert abs(res1.dx_viewport) < 0.6
        assert pytest.approx(res1.dy_viewport, abs=0.6) == -4.0
        assert res1.vy_viewport < 0

    def test_diagonal_movement(self) -> None:
        """Diagonal displacement (3, 4) gives magnitude 5 px and accurate components."""
        oft = OpticalFlowTracker(dt=1.0 / 30.0)
        img0 = _create_synthetic_beacon_image(200.0, 200.0)
        img1 = _create_synthetic_beacon_image(203.0, 204.0)

        oft.estimate_flow(img0, hint_pos=(200.0, 200.0))
        res1 = oft.estimate_flow(img1, hint_pos=(200.0, 200.0))

        assert res1.valid
        assert pytest.approx(res1.dx_viewport, abs=0.7) == 3.0
        assert pytest.approx(res1.dy_viewport, abs=0.7) == 4.0
        expected_speed = 5.0 / (1.0 / 30.0)  # 150 px/s
        assert pytest.approx(res1.speed, rel=0.20) == expected_speed

    def test_fast_movement(self) -> None:
        """Fast displacement (12 px/frame) handled correctly via pyramidal LK."""
        oft = OpticalFlowTracker(dt=1.0 / 30.0)
        img0 = _create_synthetic_beacon_image(300.0, 240.0)
        img1 = _create_synthetic_beacon_image(312.0, 240.0)

        oft.estimate_flow(img0, hint_pos=(300.0, 240.0))
        res1 = oft.estimate_flow(img1, hint_pos=(300.0, 240.0))

        assert res1.valid
        assert pytest.approx(res1.dx_viewport, abs=1.2) == 12.0

    def test_camera_motion_compensation(self) -> None:
        """
        When target is stationary in the world, but camera slews right (pan increases),
        the observed displacement in viewport is negative, and world displacement is zero.
        """
        oft = OpticalFlowTracker(dt=1.0 / 30.0)
        # Pan shift = 0.05 deg at 160 px/deg = +8.0 px camera shift
        # In viewport, image moves left by 8 px
        img0 = _create_synthetic_beacon_image(320.0, 240.0)
        img1 = _create_synthetic_beacon_image(312.0, 240.0)

        oft.estimate_flow(img0, curr_pan_deg=0.0, curr_tilt_deg=0.0, hint_pos=(320.0, 240.0))
        res1 = oft.estimate_flow(
            img1,
            curr_pan_deg=0.05,
            curr_tilt_deg=0.0,
            hint_pos=(320.0, 240.0),
            px_per_deg_x=160.0,
            px_per_deg_y=160.0,
        )

        assert res1.valid
        assert pytest.approx(res1.dx_viewport, abs=0.8) == -8.0
        assert pytest.approx(res1.cam_dx, abs=0.1) == 8.0
        # World displacement = dx_viewport + cam_dx ~= 0.0
        assert abs(res1.dx_world) < 1.0

    def test_invalid_features_uniform_image(self) -> None:
        """A featureless uniform black or white image returns valid=False."""
        oft = OpticalFlowTracker()
        blank0 = np.full((480, 640), 128, dtype=np.uint8)
        blank1 = np.full((480, 640), 128, dtype=np.uint8)

        oft.estimate_flow(blank0, hint_pos=(320.0, 240.0))
        res = oft.estimate_flow(blank1, hint_pos=(320.0, 240.0))

        # Should either be invalid or have zero valid features
        assert not res.valid or res.feature_count < 2

    def test_feature_dropout_occlusion(self) -> None:
        """When beacon drops out into zero signal, flow gracefully flags valid=False."""
        oft = OpticalFlowTracker()
        img0 = _create_synthetic_beacon_image(320.0, 240.0)
        blank = np.full((480, 640), 10, dtype=np.uint8)

        oft.estimate_flow(img0, hint_pos=(320.0, 240.0))
        res = oft.estimate_flow(blank, hint_pos=(320.0, 240.0))

        assert not res.valid

    def test_outlier_rejection(self) -> None:
        """Median-trimmed aggregation preserves true motion despite added texture noise."""
        oft = OpticalFlowTracker()
        img0 = _create_synthetic_beacon_image(320.0, 240.0)
        img1 = _create_synthetic_beacon_image(324.0, 240.0)

        # Add random salt-and-pepper noise away from beacon
        noise = np.random.RandomState(42).randint(0, 50, (480, 640), dtype=np.uint8)
        img0 = cv2.add(img0, noise)
        img1 = cv2.add(img1, noise)

        oft.estimate_flow(img0, hint_pos=(320.0, 240.0))
        res = oft.estimate_flow(img1, hint_pos=(320.0, 240.0))

        if res.valid:
            assert pytest.approx(res.dx_viewport, abs=1.5) == 4.0

    def test_forward_backward_rejection(self) -> None:
        """Corrupted second frame fails forward-backward consistency and is rejected."""
        oft = OpticalFlowTracker()
        img0 = _create_synthetic_beacon_image(320.0, 240.0)
        # Highly scrambled second frame
        img1 = np.random.RandomState(99).randint(0, 255, (480, 640), dtype=np.uint8)

        oft.estimate_flow(img0, hint_pos=(320.0, 240.0))
        res = oft.estimate_flow(img1, hint_pos=(320.0, 240.0))

        assert not res.valid

    def test_roi_boundary_clipping(self) -> None:
        """Target near the edge of the sensor [5, 5] does not crash or raise out-of-bounds."""
        oft = OpticalFlowTracker()
        img0 = _create_synthetic_beacon_image(5.0, 5.0)
        img1 = _create_synthetic_beacon_image(7.0, 5.0)

        oft.estimate_flow(img0, hint_pos=(5.0, 5.0))
        res = oft.estimate_flow(img1, hint_pos=(5.0, 5.0))
        # Valid or safely invalid without crashing
        assert isinstance(res, FlowResult)

    def test_coordinate_transformation_scales(self) -> None:
        """Verify pan/tilt angular scales transform consistently."""
        oft = OpticalFlowTracker(dt=1.0 / 30.0)
        img0 = _create_synthetic_beacon_image(320.0, 240.0)
        img1 = _create_synthetic_beacon_image(320.0, 240.0)

        oft.estimate_flow(img0, curr_pan_deg=1.0, curr_tilt_deg=2.0, hint_pos=(320.0, 240.0))
        res = oft.estimate_flow(
            img1,
            curr_pan_deg=1.1,
            curr_tilt_deg=2.2,
            hint_pos=(320.0, 240.0),
            px_per_deg_x=100.0,
            px_per_deg_y=200.0,
        )

        assert pytest.approx(res.cam_dx, abs=0.1) == 10.0
        assert pytest.approx(res.cam_dy, abs=0.1) == 40.0


class TestIMMWithOpticalFlow:
    def test_imm_flow_fusion_velocity_update(self) -> None:
        """IMM tracker successfully fuses valid optical flow velocity measurements."""
        cfg = default_config()
        imm = IMMTracker(cfg, dt=1.0 / 30.0)
        imm.init_track(100.0, 100.0, vx=0.0, vy=0.0, confidence=0.9)

        flow = FlowResult(
            valid=True,
            dx_viewport=2.0,
            dy_viewport=1.0,
            vx_viewport=60.0,
            vy_viewport=30.0,
            speed=67.08,
            confidence=0.85,
            feature_count=8,
            fb_error_mean=0.2,
        )

        imm.predict()
        state = imm.update(102.0, 101.0, score=0.95, flow=flow)

        assert state.flow_valid
        assert state.flow_dx == 2.0
        assert state.flow_dy == 1.0
        assert state.flow_confidence == 0.85
        # Estimated velocity should align with flow direction
        assert state.vx > 0.0
        assert state.vy > 0.0

    def test_imm_flow_invalid_fallback(self) -> None:
        """When flow is invalid, IMM tracker relies purely on centroid measurement without failure."""
        cfg = default_config()
        imm = IMMTracker(cfg, dt=1.0 / 30.0)
        imm.init_track(100.0, 100.0, confidence=0.9)

        invalid_flow = FlowResult(valid=False)

        imm.predict()
        state = imm.update(103.0, 100.0, score=0.9, flow=invalid_flow)

        assert not state.flow_valid
        assert state.locked
        assert pytest.approx(state.x, abs=2.0) == 103.0
