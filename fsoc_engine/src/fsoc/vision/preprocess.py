"""
src/fsoc/vision/preprocess.py
==============================
Image Preprocessing Pipeline for FSOC Beacon Spot Detection.
Handles severe environmental disturbances:
- Salt & Pepper noise (~10%) via Median Filtering
- Clouds, Haze & Non-uniform illumination via White Top-Hat background suppression
- Dynamic illumination & low-light via MAD (Median Absolute Deviation) adaptive thresholding.
"""
from __future__ import annotations
import cv2
import numpy as np
from ..core.config import PreprocessConfig, AppConfig


class AdaptiveMedianFilter:
    """
    Applies median filtering to eliminate impulsive noise (Salt & Pepper)
    while preserving beacon spot boundaries and sub-pixel energy distribution.
    """
    def __init__(self, ksize: int = 3) -> None:
        if ksize % 2 == 0 or ksize < 1:
            raise ValueError(f"ksize must be an odd positive integer, got {ksize}")
        self.ksize = ksize

    def apply(self, image: np.ndarray) -> np.ndarray:
        """Filter salt & pepper noise impulses."""
        if self.ksize == 1:
            return image.copy()
        return cv2.medianBlur(image, self.ksize)


class BackgroundSubtractor:
    """
    Suppresses slowly varying background gradients, diffuse cloud reflections,
    and atmospheric haze using morphological White Top-Hat filtering.
    
    White Top-Hat = Image - Opening(Image).
    Since beacon spots are compact (< 20 px) and clouds/haze are spatially extended,
    Top-Hat isolates the beacon spot with zero residual background floor.
    """
    def __init__(self, ksize: int = 21, enabled: bool = True) -> None:
        self.ksize = ksize
        self.enabled = enabled
        if self.enabled:
            # Elliptical / circular structuring element for isotropic response
            self.kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (self.ksize, self.ksize)
            )

    def apply(self, image: np.ndarray) -> np.ndarray:
        """Apply top-hat background subtraction."""
        if not self.enabled or self.ksize <= 1:
            return image.copy()
        return cv2.morphologyEx(image, cv2.MORPH_TOPHAT, self.kernel)


class MADThreshold:
    """
    Median Absolute Deviation (MAD) Adaptive Outlier Thresholding.
    Beacon spots in space/sky scenes are bright statistical outliers against
    a background noise floor.
    
    Formula:
        med = median(I)
        MAD = median(|I - med|)
        threshold = max(min_thresh, med + k * 1.4826 * MAD)
    """
    def __init__(self, mad_k: float = 3.5, min_threshold: int = 25) -> None:
        self.mad_k = float(mad_k)
        self.min_threshold = int(min_threshold)

    def compute_threshold(self, image: np.ndarray) -> float:
        """Compute the dynamic cutoff value for the given image with sub-millisecond histogram MAD."""
        if image.dtype == np.uint8 and image.size > 0:
            hist = cv2.calcHist([image], [0], None, [256], [0, 256]).ravel()
            cum = np.cumsum(hist)
            total = cum[-1]
            med = float(np.searchsorted(cum, total * 0.5))
            diff = np.abs(np.arange(256) - med).astype(np.int64)
            diff_hist = np.bincount(diff, weights=hist, minlength=256)
            diff_cum = np.cumsum(diff_hist)
            mad = float(np.searchsorted(diff_cum, total * 0.5))
            cutoff = med + self.mad_k * 1.4826 * mad
            return max(float(self.min_threshold), cutoff)

        flat = image.ravel()
        if flat.size > 200000:
            step = flat.size // 100000
            sample = flat[::step]
        else:
            sample = flat
            
        med = float(np.median(sample))
        mad = float(np.median(np.abs(sample - med)))
        cutoff = med + self.mad_k * 1.4826 * mad
        return max(float(self.min_threshold), cutoff)

    def apply(self, image: np.ndarray) -> tuple[np.ndarray, float]:
        """
        Threshold image into binary mask (uint8 0 or 255).
        Returns:
            (mask, threshold_value)
        """
        thresh_val = self.compute_threshold(image)
        _, mask = cv2.threshold(image, thresh_val, 255, cv2.THRESH_BINARY)
        return mask, thresh_val


class VisionPreprocessor:
    """
    Complete unified preprocessing engine combining Median Filter,
    Background Top-Hat Subtraction, and MAD Adaptive Thresholding.
    """
    def __init__(self, cfg: PreprocessConfig | AppConfig | None = None) -> None:
        if cfg is None:
            p_cfg = PreprocessConfig()
        elif isinstance(cfg, AppConfig):
            p_cfg = cfg.vision.preprocess
        elif isinstance(cfg, PreprocessConfig):
            p_cfg = cfg
        else:
            raise TypeError(f"Unsupported config type: {type(cfg)}")

        self.cfg = p_cfg
        self.median_filter = AdaptiveMedianFilter(ksize=p_cfg.median_ksize)
        self.bg_subtractor = BackgroundSubtractor(
            ksize=p_cfg.tophat_ksize, enabled=p_cfg.use_tophat
        )
        self.mad_threshold = MADThreshold(
            mad_k=p_cfg.mad_k, min_threshold=p_cfg.min_threshold
        )

    def process(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        """
        Preprocess input viewport or full frame.
        
        Args:
            image: 2D uint8 grayscale image.
            
        Returns:
            clean_image: Filtered and background-subtracted grayscale image.
            binary_mask: Binary mask with high-confidence candidate regions (0 or 255).
            threshold_val: Computed MAD cutoff.
        """
        if image.ndim != 2 or image.dtype != np.uint8:
            raise ValueError(f"Input image must be 2D uint8, got shape={image.shape}, dtype={image.dtype}")

        # Step 1: Remove Salt & Pepper impulse noise
        denoised = self.median_filter.apply(image)

        # Step 2: Subtract diffuse cloud/haze background
        cleaned = self.bg_subtractor.apply(denoised)

        # Step 3: Compute robust outlier threshold and binary mask
        mask, thresh_val = self.mad_threshold.apply(cleaned)

        return cleaned, mask, thresh_val
