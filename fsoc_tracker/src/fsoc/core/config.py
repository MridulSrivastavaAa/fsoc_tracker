"""
src/fsoc/core/config.py
=======================
Load, validate, and merge YAML configuration using Pydantic v2.
All parameters in the codebase come from here — no magic numbers.
"""
from __future__ import annotations
from pathlib import Path
from typing import Literal, Optional
import yaml
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Sub-models for each section
# ---------------------------------------------------------------------------

class SceneConfig(BaseModel):
    width: int = Field(2000, ge=640)
    height: int = Field(2000, ge=480)
    background: Literal["flat", "perlin", "stars"] = "perlin"
    seed: int = 42


class TargetConfig(BaseModel):
    shape: Literal["square", "circle", "cross"] = "square"
    size_px: int = Field(10, ge=5, le=20)
    brightness: int = Field(220, ge=50, le=255)
    psf_sigma: float = Field(1.0, ge=0.0, le=3.0)
    initial_x: Optional[float] = None
    initial_y: Optional[float] = None
    speed_px_per_s: float = Field(120.0, ge=0.0)


class LineMotionConfig(BaseModel):
    vx: float = 80.0
    vy: float = 50.0


class CircleMotionConfig(BaseModel):
    radius: float = Field(400.0, ge=10.0)
    omega_deg_per_s: float = 18.0
    # Phase offset so orbit start position is configurable.
    # Default -90° places beacon at (cx, cy-R) at t=0 i.e. directly above center.
    # Use 0° for right, 90° for below, 180° for left.
    phase_offset_deg: float = 0.0


class Figure8MotionConfig(BaseModel):
    amplitude_x: float = 400.0
    amplitude_y: float = 200.0
    omega_deg_per_s: float = 18.0


class RandomMotionConfig(BaseModel):
    max_accel: float = 20.0


class SpiralMotionConfig(BaseModel):
    r0: float = 50.0
    k: float = 2.0
    omega_deg_per_s: float = 18.0


class SinusoidalMotionConfig(BaseModel):
    vx: float = 80.0
    amplitude_y: float = 300.0
    omega_deg_per_s: float = 18.0


class UserMotionConfig(BaseModel):
    csv_path: str = "configs/user_trajectory.csv"


class MotionConfig(BaseModel):
    model: Literal["line", "circle", "figure8", "random",
                   "spiral", "sinusoidal", "user"] = "circle"
    line: LineMotionConfig = LineMotionConfig()
    circle: CircleMotionConfig = CircleMotionConfig()
    figure8: Figure8MotionConfig = Figure8MotionConfig()
    random: RandomMotionConfig = RandomMotionConfig()
    spiral: SpiralMotionConfig = SpiralMotionConfig()
    sinusoidal: SinusoidalMotionConfig = SinusoidalMotionConfig()
    user: UserMotionConfig = UserMotionConfig()


class CameraConfig(BaseModel):
    res_x: int = Field(640, ge=64)
    res_y: int = Field(480, ge=64)
    fov_x_deg: float = Field(4.0, gt=0.0)
    fov_y_deg: float = Field(3.0, gt=0.0)
    initial_cx: Optional[float] = None      # None => scene center
    initial_cy: Optional[float] = None
    max_pan_deg_per_s: float = Field(5.0, ge=1.0, le=20.0)
    max_tilt_deg_per_s: float = Field(5.0, ge=1.0, le=20.0)
    max_accel_deg_per_s2: float = Field(30.0, ge=1.0)
    latency_frames: int = Field(1, ge=0, le=5)

    @property
    def px_per_deg_x(self) -> float:
        return self.res_x / self.fov_x_deg

    @property
    def px_per_deg_y(self) -> float:
        return self.res_y / self.fov_y_deg

    @property
    def half_w(self) -> float:
        return self.res_x / 2.0

    @property
    def half_h(self) -> float:
        return self.res_y / 2.0


class PipelineConfig(BaseModel):
    fps: float = Field(30.0, ge=20.0)
    duration_s: float = Field(60.0, ge=1.0)
    seed: int = 42

    @property
    def dt(self) -> float:
        return 1.0 / self.fps


class PreprocessConfig(BaseModel):
    median_ksize: int = Field(3, ge=1)
    use_tophat: bool = True
    tophat_ksize: int = Field(21, ge=3)
    mad_k: float = Field(3.5, ge=1.0)
    min_threshold: int = Field(25, ge=0, le=255)


class DetectorConfig(BaseModel):
    min_area: float = Field(2.0, ge=1.0)
    max_area: float = Field(500.0, ge=5.0)
    min_intensity: float = Field(30.0, ge=0.0)
    max_eccentricity: float = Field(0.95, ge=0.0, le=1.0)
    subpixel_window: int = Field(5, ge=3)


class WideSearchConfig(BaseModel):
    downscale_factor: int = Field(4, ge=1)
    coarse_threshold: int = Field(40, ge=1)
    max_candidates: int = Field(5, ge=1)


class CNNVerifierConfig(BaseModel):
    model_path: str = "models/beacon_verifier.onnx"
    patch_size: int = Field(32, ge=8)
    min_confidence: float = Field(0.5, ge=0.0, le=1.0)
    enabled: bool = True


class VisionConfig(BaseModel):
    preprocess: PreprocessConfig = PreprocessConfig()
    detector: DetectorConfig = DetectorConfig()
    wide_search: WideSearchConfig = WideSearchConfig()
    cnn: CNNVerifierConfig = CNNVerifierConfig()


class TrackingConfig(BaseModel):
    q_pos: float = Field(1.0, ge=0.01)
    q_vel: float = Field(2.0, ge=0.01)
    r_pos: float = Field(4.0, ge=0.1)
    gate_dist_px: float = Field(60.0, ge=5.0)
    consecutive_acquire_frames: int = Field(3, ge=1)
    consecutive_lost_frames: int = Field(10, ge=1)
    reacquire_timeout_frames: int = Field(45, ge=5)
    max_coast_frames: int = Field(15, ge=1)


class ControlConfig(BaseModel):
    # PID gains tuned for ISRO R14 ≤10 px boresight spec.
    # Analytical basis: actuator scale = 160 px/deg, max_rate = 5 deg/s = 800 px/s
    # Kp_min for 125 px/s tracking without saturation: 125/800 * scale ≈ 3.2
    # Kp=3.5 gives ~90% loop bandwidth while remaining stable.
    # Ki=0.6 eliminates steady-state bias from integrator lag.
    # Kd=0.25 provides moderate derivative damping without noise amplification.
    kp: float = Field(3.5, ge=0.0)
    ki: float = Field(0.6, ge=0.0)
    kd: float = Field(0.25, ge=0.0)
    kff: float = Field(0.9, ge=0.0)
    anti_windup_limit: float = Field(5.0, ge=0.1)
    deadband_px: float = Field(0.5, ge=0.0)
    target_offset_x: float = 0.0
    target_offset_y: float = 0.0


class AdvancedConfig(BaseModel):
    enabled: bool = True
    scintillation_window_frames: int = Field(30, ge=5)
    fade_threshold_ratio: float = Field(0.35, ge=0.05, le=0.9)
    wander_cutoff_hz: float = Field(3.0, ge=0.5, le=15.0)
    adaptive_kalman_gain: float = Field(1.5, ge=0.1)


# ---------------------------------------------------------------------------
# Root config — single source of truth
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    """Top-level configuration object. All modules receive this."""
    scene: SceneConfig = SceneConfig()
    target: TargetConfig = TargetConfig()
    motion: MotionConfig = MotionConfig()
    camera: CameraConfig = CameraConfig()
    pipeline: PipelineConfig = PipelineConfig()
    vision: VisionConfig = VisionConfig()
    tracking: TrackingConfig = TrackingConfig()
    control: ControlConfig = ControlConfig()
    advanced: AdvancedConfig = AdvancedConfig()



# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config(yaml_path: str | Path) -> AppConfig:
    """
    Load a YAML file and return a validated AppConfig.
    Missing keys fall back to model defaults.
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw: dict = yaml.safe_load(f) or {}

    return AppConfig.model_validate(raw)


def default_config() -> AppConfig:
    """Return an AppConfig with all defaults (no YAML file needed)."""
    return AppConfig()
