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
    area_px: float = 10.0           # blob area in pixels
    score: float = 1.0              # CNN verifier score 0..1 (default 1 = no CNN)

    def to_point(self) -> Point:
        return Point(self.x, self.y)


# ---------------------------------------------------------------------------
# Optical Flow output
# ---------------------------------------------------------------------------

@dataclass
class FlowResult:
    """Output of local sparse optical flow estimator."""
    valid: bool = False
    dx_viewport: float = 0.0         # frame-to-frame displacement in viewport px
    dy_viewport: float = 0.0
    vx_viewport: float = 0.0         # velocity in viewport px/s
    vy_viewport: float = 0.0
    dx_world: float = 0.0            # camera-motion compensated displacement
    dy_world: float = 0.0
    vx_world: float = 0.0            # camera-motion compensated velocity px/s
    vy_world: float = 0.0
    speed: float = 0.0               # magnitude in px/s
    confidence: float = 0.0          # flow quality score 0..1
    feature_count: int = 0           # surviving verified features
    fb_error_mean: float = 0.0       # mean forward-backward consistency error (px)
    cam_dx: float = 0.0              # camera slew shift (px)
    cam_dy: float = 0.0
    weight: float = 0.0              # adaptive trust weight in [0, 1]
    quality: float = 0.0             # raw flow quality metric in [0, 1]
    innovation: float = 0.0          # velocity innovation NIS
    jitter_score: float = 0.0        # high-frequency camera jitter intensity
    gate_reason: str = "NO_FLOW"     # GOOD_FLOW | LOW_FEATURE_COUNT | HIGH_FB_ERROR | HIGH_INNOVATION | HIGH_JITTER | INVALID_FLOW | NO_FLOW


# ---------------------------------------------------------------------------
# Tracker output
# ---------------------------------------------------------------------------

@dataclass
class TrackState:
    """Kalman / IMM filter estimate output."""
    x: float                        # estimated position x (viewport px)
    y: float                        # estimated position y (viewport px)
    vx: float                       # estimated velocity x (px/frame)
    vy: float                       # estimated velocity y (px/frame)
    confidence: float               # track quality 0..1
    locked: bool                    # True = actively tracking
    prob_cv: float = 0.0            # IMM probability for Constant Velocity model
    prob_ct: float = 0.0            # IMM probability for Constant Turn model
    prob_rw: float = 0.0            # IMM probability for Random Walk model
    dominant_model: str = "CV"      # Dominant IMM model name ("CV", "CT", "RW")
    innovation: float = 0.0         # Innovation residual magnitude (px)
    uncertainty: float = 0.0        # Estimated position uncertainty std (px)
    flow_valid: bool = False        # Optical flow active for this estimate
    flow_dx: float = 0.0            # Measured optical flow dx (px)
    flow_dy: float = 0.0            # Measured optical flow dy (px)
    flow_speed: float = 0.0         # Optical flow speed (px/s)
    flow_confidence: float = 0.0    # Optical flow confidence (0..1)
    flow_feature_count: int = 0     # Optical flow inlier feature count
    flow_fb_error: float = 0.0      # Forward-backward error (px)
    flow_weight: float = 0.0        # Adaptive fusion weight [0, 1]
    flow_quality: float = 0.0       # Flow quality score [0, 1]
    flow_innovation: float = 0.0    # Flow velocity innovation NIS
    jitter_score: float = 0.0       # Detected camera jitter magnitude
    flow_gate_reason: str = "NO_FLOW" # Gating reason code
    pf_active: bool = False         # Particle filter recovery active
    pf_particles: int = 0           # Active particle count
    pf_cluster_std: float = 0.0     # Particle spatial cluster dispersion (px)
    pf_n_eff: float = 0.0           # Effective sample size N_eff
    pf_reacquired: bool = False     # Target recovery confirmed in this frame


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
    prob_cv: float = 0.0                # IMM model probabilities
    prob_ct: float = 0.0
    prob_rw: float = 0.0
    dominant_model: str = "CV"
    flow_valid: bool = False            # Optical flow active
    flow_dx: float = 0.0
    flow_dy: float = 0.0
    flow_speed: float = 0.0
    flow_confidence: float = 0.0
    flow_feature_count: int = 0
    flow_fb_error: float = 0.0
    flow_weight: float = 0.0
    flow_quality: float = 0.0
    flow_innovation: float = 0.0
    jitter_score: float = 0.0
    flow_gate_reason: str = "NO_FLOW"
    pf_active: bool = False
    pf_particles: int = 0
    pf_cluster_std: float = 0.0
    pf_n_eff: float = 0.0
    pf_reacquired: bool = False


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
    reacquisition_success_pct: float = 0.0
    reacquisition_time_mean_s: Optional[float] = None
    reacquisition_time_p95_s: Optional[float] = None
    reacquisition_time_max_s: Optional[float] = None
    false_reacquisition_count: int = 0
    error_mean_px: float = 0.0
    error_max_px: float = 0.0
    error_rmse_px: float = 0.0
    lock_retention_pct: float = 0.0
    target_loss_pct: float = 0.0
    proc_ms_mean: float = 0.0
    proc_ms_p95: float = 0.0
