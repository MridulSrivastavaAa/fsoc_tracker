"""
src/fsoc/core/types.py
======================
Shared typed dataclasses used as communication contracts between all modules.
No module imports from another module's internals — they only share these types.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Point:
    """A 2-D position in pixel coordinates (x right, y down)."""
    x: float
    y: float

    def __sub__(self, other: "Point") -> "Point":
        return Point(self.x - other.x, self.y - other.y)

    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y)

    def norm(self) -> float:
        """Euclidean distance from origin."""
        return float(np.sqrt(self.x ** 2 + self.y ** 2))

    def to_array(self) -> np.ndarray:
        return np.array([self.x, self.y], dtype=np.float64)


# ---------------------------------------------------------------------------
# Full-frame data (output of FrameSource)
# ---------------------------------------------------------------------------

@dataclass
class FullFrame:
    """
    One rendered frame of the 2000x2000 full scene.
    ground_truth is None when using a video file source (no GT available).
    """
    image: np.ndarray               # shape (H, W) uint8, full scene
    frame_index: int                # 0-based
    timestamp_s: float              # simulation time in seconds
    ground_truth: Optional[list[Point]] = None   # beacon positions in screen coords


# ---------------------------------------------------------------------------
# Camera viewport output
# ---------------------------------------------------------------------------

@dataclass
class ViewportFrame:
    """
    The 640x480 image seen through the virtual camera viewport.
    Also carries camera state at the time of rendering.
    """
    image: np.ndarray               # shape (480, 640) uint8
    frame_index: int
    timestamp_s: float
    pan_deg: float                  # current pan angle in degrees
    tilt_deg: float                 # current tilt angle in degrees
    cx_px: float                    # viewport centre in screen pixels (x)
    cy_px: float                    # viewport centre in screen pixels (y)
    ground_truth_viewport: Optional[list[Point]] = None  # GT in viewport coords


# ---------------------------------------------------------------------------
# Detector output
# ---------------------------------------------------------------------------

@dataclass
class Detection:
    """
    A single candidate detected by the vision pipeline.
    Coordinates are in viewport pixel space.
    """
    x: float                        # sub-pixel centroid x (viewport)
    y: float                        # sub-pixel centroid y (viewport)
    intensity: float                # peak intensity of the blob
    area_px: float                  # blob area in pixels
    score: float = 1.0              # CNN verifier score 0..1 (default 1 = no CNN)

    def to_point(self) -> Point:
        return Point(self.x, self.y)


# ---------------------------------------------------------------------------
# Tracker output
# ---------------------------------------------------------------------------

@dataclass
class TrackState:
    """Kalman filter estimate output."""
    x: float                        # estimated position x (viewport px)
    y: float                        # estimated position y (viewport px)
    vx: float                       # estimated velocity x (px/frame)
    vy: float                       # estimated velocity y (px/frame)
    confidence: float               # track quality 0..1
    locked: bool                    # True = actively tracking


# ---------------------------------------------------------------------------
# Control command
# ---------------------------------------------------------------------------

@dataclass
class CameraCommand:
    """Rate command sent to the virtual pan-tilt actuator."""
    pan_rate_deg_per_s: float = 0.0
    tilt_rate_deg_per_s: float = 0.0


# ---------------------------------------------------------------------------
# Per-frame metrics
# ---------------------------------------------------------------------------

@dataclass
class FrameMetrics:
    """All logged quantities for a single frame."""
    frame_index: int
    timestamp_s: float
    state: str                          # SEARCH | ACQUIRE | TRACK | LOST | REACQUIRE
    est_x: Optional[float] = None       # screen coords
    est_y: Optional[float] = None
    gt_x: Optional[float] = None        # ground truth screen coords
    gt_y: Optional[float] = None
    # Centroiding/estimation accuracy: |Kalman_estimate − GT_viewport|
    # Measures how well the Kalman filter tracks the beacon in sensor space.
    error_px: Optional[float] = None
    # ISRO R14 boresight alignment error: distance from target to optical axis (320,240).
    # This is the primary mission-compliance metric. R14 spec requires ≤ 10 px.
    boresight_px: Optional[float] = None
    confidence: float = 0.0
    locked: bool = False
    proc_ms: float = 0.0                # processing time
    pan_deg: float = 0.0
    tilt_deg: float = 0.0


# ---------------------------------------------------------------------------
# Summary statistics (end of run)
# ---------------------------------------------------------------------------

@dataclass
class RunSummary:
    """Aggregate performance for one complete simulation run."""
    duration_s: float = 0.0
    fps_mean: float = 0.0
    fps_min: float = 0.0
    acquisition_time_s: Optional[float] = None
    reacquisition_times_s: list[float] = field(default_factory=list)
    error_mean_px: float = 0.0
    error_max_px: float = 0.0
    error_rmse_px: float = 0.0
    lock_retention_pct: float = 0.0
    target_loss_pct: float = 0.0
    proc_ms_mean: float = 0.0
    proc_ms_p95: float = 0.0
