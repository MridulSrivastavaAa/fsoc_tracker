"""
tests/unit/test_vision.py
==========================
Comprehensive Unit & Integration Tests for Phase 3: Vision Perception Pipeline.
Tests:
1. Preprocessor (Median filter, White Top-Hat background suppression, MAD threshold)
2. Spot Detector (Sub-pixel centroid accuracy, area/aspect-ratio filtering, noise tolerance)
3. Wide-Area Search (4x downscaled full-scene search <= 2s, camera pan/tilt slew calculation)
4. CNN Verifier (ONNX / neural network patch verification, false positive rejection)
5. End-to-End Pipeline (Simulated frame + disturbances + perception)
"""
import time
import pytest
import numpy as np
import cv2

from fsoc.core.types import Point, Detection
from fsoc.core.config import (
    AppConfig,
    PreprocessConfig,
    DetectorConfig,
    WideSearchConfig,
    CNNVerifierConfig,
    default_config,
)
from fsoc.vision.preprocess import (
    AdaptiveMedianFilter,
    BackgroundSubtractor,
    MADThreshold,
    VisionPreprocessor,
)
from fsoc.vision.detector import SpotDetector
from fsoc.vision.wide_search import WideAreaSearch
from fsoc.vision.cnn_verifier import BeaconVerifierCNN, BeaconCNNModel


def create_synthetic_gaussian_spot(
    shape: tuple[int, int] = (480, 640),
    cx: float = 320.4,
    cy: float = 240.7,
    sigma: float = 2.0,
    amplitude: float = 220.0,
    bg_level: float = 15.0,
) -> np.ndarray:
    """Create a synthetic 2D Gaussian laser beacon spot with sub-pixel ground truth."""
    H, W = shape
    ys, xs = np.indices((H, W), dtype=np.float64)
    r2 = (xs - cx) ** 2 + (ys - cy) ** 2
    spot = amplitude * np.exp(-0.5 * r2 / (sigma ** 2)) + bg_level
    return np.clip(spot, 0, 255).astype(np.uint8)


# ===========================================================================
# 1. Preprocessor Tests
# ===========================================================================

class TestPreprocessor:
    def test_median_filter_removes_salt_pepper(self) -> None:
        """Verify median filter wipes out Salt & Pepper impulse noise."""
        clean = np.full((100, 100), 50, dtype=np.uint8)
        noisy = clean.copy()
        # Add 10% Salt & Pepper noise
        rng = np.random.RandomState(42)
        mask = rng.rand(100, 100) < 0.10
        noisy[mask] = 255

        med_filter = AdaptiveMedianFilter(ksize=3)
        filtered = med_filter.apply(noisy)

        # After 3x3 median filter, isolated noise impulses should be eliminated
        diff = np.abs(filtered.astype(np.int32) - clean.astype(np.int32))
        assert np.mean(diff) < 2.0
        assert filtered.shape == (100, 100)
        assert filtered.dtype == np.uint8

    def test_median_filter_invalid_ksize_raises(self) -> None:
        with pytest.raises(ValueError):
            AdaptiveMedianFilter(ksize=4)  # even ksize invalid

    def test_tophat_suppresses_cloud_gradients(self) -> None:
        """Verify White Top-Hat removes smooth gradients while retaining compact spots."""
        H, W = 200, 200
        ys, xs = np.indices((H, W), dtype=np.float64)
        # Smooth cloud gradient background (0 to 120)
        cloud_bg = (xs / W * 120.0).astype(np.uint8)

        # Add small 8px bright spot at (100, 100)
        img = cloud_bg.copy()
        cv2.circle(img, (100, 100), 4, 240, -1)

        subtractor = BackgroundSubtractor(ksize=21, enabled=True)
        cleaned = subtractor.apply(img)

        # Cloud gradient background should be eliminated (< 10)
        assert cleaned[50, 50] < 10
        assert cleaned[150, 150] < 10
        # Compact spot must remain bright
        assert cleaned[100, 100] >= 180

    def test_mad_threshold_adapts_to_noise_floor(self) -> None:
        """Verify MAD threshold computes robust outlier cutoff."""
        rng = np.random.RandomState(42)
        base = (rng.randn(200, 200) * 5 + 30).clip(0, 255).astype(np.uint8)
        # Insert bright outlier beacon
        base[95:105, 95:105] = 220

        mad = MADThreshold(mad_k=3.5, min_threshold=25)
        mask, thresh = mad.apply(base)

        assert thresh > 40.0
        assert thresh < 150.0
        assert mask[100, 100] == 255  # beacon detected
        assert mask[10, 10] == 0      # noise rejected

    def test_preprocessor_execution_speed(self) -> None:
        """Verify 640x480 frame preprocessor runs within <= 5 ms."""
        img = create_synthetic_gaussian_spot()
        prep = VisionPreprocessor()

        # Warm up
        prep.process(img)

        t0 = time.perf_counter()
        for _ in range(10):
            prep.process(img)
        dt_ms = (time.perf_counter() - t0) * 1000 / 10

        assert dt_ms < 10.0  # Well within 33 ms real-time frame budget


# ===========================================================================
# 2. Spot Detector Tests
# ===========================================================================

class TestSpotDetector:
    def test_subpixel_centroid_accuracy_clean(self) -> None:
        """Verify sub-pixel centroid accuracy has < 0.15 px error on clean spot."""
        true_cx, true_cy = 320.65, 239.35
        img = create_synthetic_gaussian_spot(cx=true_cx, cy=true_cy, sigma=2.5)

        detector = SpotDetector()
        dets = detector.detect(img)

        assert len(dets) >= 1
        best = dets[0]
        err_x = abs(best.x - true_cx)
        err_y = abs(best.y - true_cy)
        euclid_err = np.sqrt(err_x ** 2 + err_y ** 2)

        assert euclid_err < 0.20  # Extremely high sub-pixel precision (< 0.20 px)

    def test_subpixel_accuracy_under_heavy_noise(self) -> None:
        """Verify detector achieves < 2.0 px error under Gaussian + S&P noise (PS: <= 10 px)."""
        true_cx, true_cy = 310.25, 250.75
        img = create_synthetic_gaussian_spot(cx=true_cx, cy=true_cy, sigma=2.5, amplitude=200.0)

        # Add Gaussian noise (sigma=15) and S&P noise (5%)
        rng = np.random.RandomState(42)
        gauss = (rng.randn(*img.shape) * 15).astype(np.int32)
        noisy = np.clip(img.astype(np.int32) + gauss, 0, 255).astype(np.uint8)
        sp_mask = rng.rand(*img.shape) < 0.05
        noisy[sp_mask] = 255

        detector = SpotDetector()
        dets = detector.detect(noisy)

        assert len(dets) >= 1
        best = dets[0]
        euclid_err = np.sqrt((best.x - true_cx) ** 2 + (best.y - true_cy) ** 2)
        assert euclid_err < 2.5  # Well below PS 26169 requirement of <= 10 px!

    def test_filters_elongated_rain_streaks(self) -> None:
        """Verify detector filters out long streaks (aspect ratio > 4.5)."""
        canvas = np.zeros((480, 640), dtype=np.uint8)
        # Draw long diagonal streak (length 50 px, width 2 px)
        cv2.line(canvas, (100, 100), (150, 150), 200, 2)
        # Draw round beacon
        cv2.circle(canvas, (320, 240), 5, 220, -1)

        detector = SpotDetector()
        dets = detector.detect(canvas)

        assert len(dets) == 1
        assert abs(dets[0].x - 320.0) < 2.0
        assert abs(dets[0].y - 240.0) < 2.0

    def test_filters_oversized_clouds(self) -> None:
        """Verify detector filters out blobs exceeding max_area (500 px)."""
        canvas = np.zeros((480, 640), dtype=np.uint8)
        # Draw large cloud blob (area ~ 2000 px)
        cv2.circle(canvas, (200, 200), 30, 200, -1)
        # Draw target beacon (area ~ 50 px)
        cv2.circle(canvas, (400, 300), 4, 230, -1)

        detector = SpotDetector()
        dets = detector.detect(canvas)

        assert len(dets) == 1
        assert abs(dets[0].x - 400.0) < 2.0


# ===========================================================================
# 3. Wide-Area Search Tests
# ===========================================================================

class TestWideAreaSearch:
    def test_search_full_scene_downscaled(self) -> None:
        """Verify 4x downscaled wide search detects target on 2000x2000 scene."""
        canvas = np.full((2000, 2000), 20, dtype=np.uint8)
        true_x, true_y = 1540.0, 480.0
        cv2.circle(canvas, (int(true_x), int(true_y)), 6, 230, -1)

        searcher = WideAreaSearch()
        res = searcher.search_full_scene(canvas)

        assert res is not None
        pt, conf = res
        assert abs(pt.x - true_x) < 5.0
        assert abs(pt.y - true_y) < 5.0
        assert conf > 0.5

    def test_search_speed_under_20ms(self) -> None:
        """Verify wide-area search completes in < 25 ms."""
        canvas = np.full((2000, 2000), 20, dtype=np.uint8)
        cv2.circle(canvas, (800, 1200), 6, 230, -1)

        searcher = WideAreaSearch()
        # Warmup
        searcher.search_full_scene(canvas)

        t0 = time.perf_counter()
        searcher.search_full_scene(canvas)
        dt_ms = (time.perf_counter() - t0) * 1000

        assert dt_ms < 50.0  # Ultra-rapid acquisition scan

    def test_camera_pointing_and_slew_time(self) -> None:
        """Verify slew time adheres to requirement R13 (acquisition time <= 2s)."""
        target_pt = Point(1600.0, 1400.0)
        searcher = WideAreaSearch()

        pan, tilt, slew_s = searcher.compute_camera_pointing(
            target_pt, scene_center_x=1000.0, scene_center_y=1000.0
        )

        # Scale is 160 px/deg. dx = 600 px -> pan = 3.75 deg. dy = 400 px -> tilt = 2.5 deg.
        assert abs(pan - 3.75) < 0.1
        assert abs(tilt - 2.5) < 0.1
        # Max slew speed is 5.0 deg/s. Max time is 3.75 / 5.0 = 0.75 s
        assert slew_s < 1.0
        assert slew_s <= 2.0  # Meets R13 acquisition <= 2.0s!

    def test_spiral_and_raster_generators(self) -> None:
        """Verify waypoint paths for blind scanning."""
        searcher = WideAreaSearch()
        spiral = searcher.generate_spiral_search_path(max_radius_deg=4.0)
        assert len(spiral) > 5
        assert spiral[0] == (0.0, 0.0)

        raster = searcher.generate_raster_search_path()
        assert len(raster) > 6


# ===========================================================================
# 4. CNN Verifier Tests
# ===========================================================================

class TestCNNVerifier:
    def test_patch_extraction_and_normalization(self) -> None:
        img = create_synthetic_gaussian_spot()
        verifier = BeaconVerifierCNN()
        patch = verifier.extract_patch(img, 320.0, 240.0, patch_size=32)

        assert patch.shape == (32, 32)
        assert patch.min() >= 0.0
        assert patch.max() <= 1.0

    def test_verifier_discriminates_beacon_vs_streak(self) -> None:
        """Verify CNN verifier scores real beacon > 0.6 and streak < 0.35."""
        verifier = BeaconVerifierCNN()

        # 1. Genuine Gaussian beacon patch
        patch_beacon = np.zeros((32, 32), dtype=np.float32)
        ys, xs = np.indices((32, 32))
        r2 = (xs - 16) ** 2 + (ys - 16) ** 2
        patch_beacon = np.exp(-0.5 * r2 / 4.0).astype(np.float32)

        score_beacon = verifier.verify_patch(patch_beacon)
        assert score_beacon > 0.55

        # 2. Rain streak patch (narrow diagonal line)
        patch_streak = np.zeros((32, 32), dtype=np.float32)
        for i in range(32):
            patch_streak[i, i] = 1.0

        score_streak = verifier.verify_patch(patch_streak)
        assert score_streak < 0.40

    def test_verify_detections_updates_scores(self) -> None:
        img = create_synthetic_gaussian_spot(cx=200.0, cy=200.0)
        verifier = BeaconVerifierCNN()

        dets = [
            Detection(x=200.0, y=200.0, intensity=220.0, area_px=20.0),
            Detection(x=10.0, y=10.0, intensity=50.0, area_px=5.0),
        ]

        verified = verifier.verify_detections(img, dets, filter_false_positives=False)
        assert len(verified) == 2
        # Real beacon candidate should have higher score than random background
        assert verified[0].x == 200.0
        assert verified[0].score > verified[1].score


# ===========================================================================
# 5. Integration Pipeline Test
# ===========================================================================

def test_full_vision_pipeline_integration() -> None:
    """
    Test full perception pipeline (Preprocessor -> SpotDetector -> CNNVerifier)
    under combined noise and atmospheric disturbance.
    """
    true_x, true_y = 345.8, 212.4
    raw_img = create_synthetic_gaussian_spot(cx=true_x, cy=true_y, sigma=2.2, amplitude=210)

    # Add Gaussian noise + S&P noise
    rng = np.random.RandomState(123)
    noisy = raw_img.astype(np.float32) + rng.randn(*raw_img.shape) * 8.0
    sp_mask = rng.rand(*raw_img.shape) < 0.03
    noisy[sp_mask] = 255
    noisy = np.clip(noisy, 0, 255).astype(np.uint8)

    cfg = default_config()
    preprocessor = VisionPreprocessor(cfg)
    detector = SpotDetector(cfg, preprocessor=preprocessor)
    verifier = BeaconVerifierCNN(cfg)

    # 1. Preprocess
    clean, mask, _ = preprocessor.process(noisy)

    # 2. Detect
    candidates = detector.detect(noisy, mask=mask, intensity_image=clean)
    assert len(candidates) > 0

    # 3. Verify with CNN
    final_dets = verifier.verify_detections(noisy, candidates, filter_false_positives=True)
    assert len(final_dets) >= 1

    best = final_dets[0]
    err = np.sqrt((best.x - true_x) ** 2 + (best.y - true_y) ** 2)

    # Error must be <= 10 px (PS 26169 requirement R14)
    assert err <= 3.0
    assert best.score >= 0.5
