"""
src/fsoc/vision/detector.py
============================
Sub-Pixel Beacon Spot Detector for FSOC Optical Terminals.
Uses Connected Components Analysis (CCA) and Intensity-Weighted Centroiding
(Center-of-Gravity) to achieve sub-pixel tracking accuracy (error < 0.2 px clean, < 2 px noisy,
well below the PS requirement of <= 10 px).
"""
from __future__ import annotations
from typing import Optional
import cv2
import numpy as np

from ..core.types import Detection, Point
from ..core.config import DetectorConfig, AppConfig
from .preprocess import VisionPreprocessor


class SpotDetector:
    """
    Detects beacon laser spots in a viewport frame with sub-pixel precision.
    Filters out noise clusters, hot pixels, and atmospheric rain streaks using
    geometric area and aspect-ratio constraints.
    """
    def __init__(
        self,
        cfg: DetectorConfig | AppConfig | None = None,
        preprocessor: Optional[VisionPreprocessor] = None,
    ) -> None:
        if cfg is None:
            d_cfg = DetectorConfig()
        elif isinstance(cfg, AppConfig):
            d_cfg = cfg.vision.detector
        elif isinstance(cfg, DetectorConfig):
            d_cfg = cfg
        else:
            raise TypeError(f"Unsupported config type: {type(cfg)}")

        self.cfg = d_cfg
        self.preprocessor = preprocessor or VisionPreprocessor(cfg)

    def compute_subpixel_centroid(
        self,
        image: np.ndarray,
        x0: int,
        y0: int,
        w: int,
        h: int,
        pad: int = 2,
    ) -> tuple[float, float, float]:
        """
        Compute sub-pixel centroid (CoG) within bounding box with safety padding.
        
        Formula:
            x_c = sum(x * I(x, y)) / sum(I(x, y))
            y_c = sum(y * I(x, y)) / sum(I(x, y))
            
        Returns:
            (sub_x, sub_y, peak_intensity)
        """
        H, W = image.shape
        x_min = max(0, x0 - pad)
        y_min = max(0, y0 - pad)
        x_max = min(W, x0 + w + pad)
        y_max = min(H, y0 + h + pad)

        roi = image[y_min:y_max, x_min:x_max].astype(np.float64)
        peak_intensity = float(np.max(roi)) if roi.size > 0 else 0.0

        # Subtract baseline floor (estimated from ROI boundary) to avoid bias
        bg_estimate = float(np.percentile(roi, 15)) if roi.size > 8 else float(np.min(roi))
        weights = np.maximum(0.0, roi - bg_estimate)

        total_weight = float(np.sum(weights))
        if total_weight <= 1e-6:
            # Fallback to geometric box center if no weight variation
            return (x0 + w / 2.0, y0 + h / 2.0, peak_intensity)

        # Coordinate grids in ROI
        ys, xs = np.indices(roi.shape, dtype=np.float64)
        local_xc = float(np.sum(xs * weights) / total_weight)
        local_yc = float(np.sum(ys * weights) / total_weight)

        sub_x = x_min + local_xc
        sub_y = y_min + local_yc

        return sub_x, sub_y, peak_intensity

    def detect(
        self,
        image: np.ndarray,
        mask: Optional[np.ndarray] = None,
        intensity_image: Optional[np.ndarray] = None,
    ) -> list[Detection]:
        """
        Detect beacon candidates in the image.
        
        Args:
            image: Input 2D uint8 image (usually raw or median-filtered).
            mask: Optional precomputed binary mask. If None, runs self.preprocessor.
            intensity_image: Grayscale image used for intensity-weighted centroid.
                             If None, uses `image`.
                             
        Returns:
            Sorted list of `Detection` instances, ordered by prominence.
        """
        if image.ndim != 2 or image.dtype != np.uint8:
            raise ValueError(f"Image must be 2D uint8, got shape={image.shape}")

        int_img = intensity_image if intensity_image is not None else image

        if mask is None:
            clean_img, bin_mask, _ = self.preprocessor.process(image)
            # Use clean_img for centroiding if no explicit intensity_image was given
            if intensity_image is None:
                int_img = clean_img
            mask = bin_mask

        # Connected Components Analysis
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )

        candidates: list[Detection] = []

        # label 0 is background; iterate through 1..num_labels-1
        for label_idx in range(1, num_labels):
            area = float(stats[label_idx, cv2.CC_STAT_AREA])
            if area < self.cfg.min_area or area > self.cfg.max_area:
                continue

            x0 = int(stats[label_idx, cv2.CC_STAT_LEFT])
            y0 = int(stats[label_idx, cv2.CC_STAT_TOP])
            w = int(stats[label_idx, cv2.CC_STAT_WIDTH])
            h = int(stats[label_idx, cv2.CC_STAT_HEIGHT])

            # Check aspect ratio / elongation to discard rain streaks or scanlines
            aspect_ratio = max(w / max(1, h), h / max(1, w))
            if aspect_ratio > 4.5:
                continue

            # Check oriented streak ratio for diagonal rain streaks
            if area > 10 and (w > 10 or h > 10):
                comp_mask = (labels[y0:y0 + h, x0:x0 + w] == label_idx)
                pts = np.argwhere(comp_mask)
                if len(pts) >= 5:
                    rect = cv2.minAreaRect(pts[:, ::-1])
                    rw, rh = rect[1]
                    if rw > 0 and rh > 0:
                        oriented_ratio = max(rw, rh) / max(0.5, min(rw, rh))
                        if oriented_ratio > 4.5:
                            continue

            # Compute intensity-weighted sub-pixel centroid
            sub_x, sub_y, peak_val = self.compute_subpixel_centroid(
                int_img, x0, y0, w, h, pad=self.cfg.subpixel_window // 2
            )

            if peak_val < self.cfg.min_intensity:
                continue

            # Calculate prominence score based on peak intensity and compactness
            prominence = float(peak_val * np.sqrt(area) / (1.0 + 0.2 * (aspect_ratio - 1.0)))

            candidates.append(
                Detection(
                    x=float(sub_x),
                    y=float(sub_y),
                    intensity=float(peak_val),
                    area_px=float(area),
                    score=prominence,
                )
            )

        # Sort candidates descending by prominence score
        candidates.sort(key=lambda d: d.score, reverse=True)
        return candidates

    def get_best_detection(
        self,
        image: np.ndarray,
        mask: Optional[np.ndarray] = None,
    ) -> Optional[Detection]:
        """Convenience method returning the highest-scoring candidate or None."""
        results = self.detect(image, mask)
        return results[0] if results else None
