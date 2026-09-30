"""
src/fsoc/vision/__init__.py
============================
Vision Perception & Acquisition Pipeline for FSOC Optical Tracking.
Phase 3 Modules:
- preprocess.py: Adaptive median filtering, background top-hat, MAD threshold
- detector.py: Connected components + intensity-weighted sub-pixel centroid
- wide_search.py: Coarse 4x downscaled acquisition (<= 2s) & spiral waypoint search
- cnn_verifier.py: ONNX lightweight CNN patch verifier (< 1 ms) for false positive rejection
"""
from .preprocess import (
    AdaptiveMedianFilter,
    BackgroundSubtractor,
    MADThreshold,
    VisionPreprocessor,
)
from .detector import SpotDetector
from .wide_search import WideAreaSearch
from .cnn_verifier import BeaconVerifierCNN
from .optical_flow import OpticalFlowTracker

__all__ = [
    "AdaptiveMedianFilter",
    "BackgroundSubtractor",
    "MADThreshold",
    "VisionPreprocessor",
    "SpotDetector",
    "WideAreaSearch",
    "BeaconVerifierCNN",
    "OpticalFlowTracker",
]
