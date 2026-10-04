"""
src/fsoc/disturbances/engine.py
================================
DisturbanceEngine: composes all disturbance modules in the correct
physical order and applies them to the full-scene image each frame.

Fixed application order (physically motivated):
  1. Platform motion  — scene-level slow drift (applied to full 2000x2000)
  2. Atmosphere       — contrast/brightness/fog/rain degradation
  3. Camera jitter    — per-frame viewport vibration (applied after crop)
  4. Noise            — sensor noise (applied last, closest to detector)

The engine owns one instance of each disturbance module.
All modules are configured at construction and can be toggled/updated
at runtime (e.g., via GUI sliders) by setting their attributes directly.
"""
from __future__ import annotations
import math
import numpy as np
import cv2
from dataclasses import dataclass

from .noise import SaltPepperNoise, GaussianNoise, PoissonNoise
from .jitter import CameraJitter
from .platform_motion import PlatformMotion
from .atmosphere import AtmosphereEffect, TurbulenceEffect


@dataclass
class DisturbanceConfig:
    """
    Flat configuration bag for the DisturbanceEngine.
    All fields match the YAML config under disturbances:
    (to be added to default.yaml in future; sensible defaults here).
    """
    # Salt & Pepper
    sp_enabled: bool = False
    sp_density: float = 0.05

    # Gaussian
    gauss_enabled: bool = False
    gauss_sigma: float = 8.0

    # Poisson
    poisson_enabled: bool = False
    poisson_gain: float = 1.0

    # Jitter
    jitter_enabled: bool = False
    jitter_max_px: float = 10.0

    # Mechanical vibration (deterministic sinusoid, driven by vibration_hz)
    vibration_px: float = 0.0
    vibration_hz: float = 8.0

    # Platform motion
    platform_enabled: bool = False
    platform_mode: str = "linear"
    platform_max_px: float = 5.0

    # Atmosphere
    atm_enabled: bool = True
    atm_condition: str = "clear"
    atm_strength: float = 1.0

    # Turbulence
    turbulence_enabled: bool = False
    turbulence_wander_px: float = 3.0
    turbulence_scint_sigma: float = 0.15
    turbulence_blur_sigma: float = 0.5

    # Wind torque: sigma of a rate disturbance applied to the gimbal axes, deg/s
    wind_deg_s: float = 0.0

    # Master seed (sub-modules get seed + offset)
    seed: int = 100
    fps: float = 30.0


class DisturbanceEngine:
    """
    Applies all disturbances to simulation frames in the correct order.

    Usage (per frame)::

        # For full-scene image (before camera crop):
        disturbed_full = engine.apply_full_scene(full_img, dt)

        # For viewport image (after camera crop):
        disturbed_view = engine.apply_viewport(viewport_img)
    """

    def __init__(
        self,
        cfg: DisturbanceConfig | None = None,
        seed: int | None = None,
    ) -> None:
        cfg = cfg or DisturbanceConfig()
        if seed is not None:
            cfg.seed = seed
        self.cfg = cfg
        s = cfg.seed


        # --- Platform motion (applied on full scene) ---
        self.platform = PlatformMotion(
            mode=cfg.platform_mode,          # type: ignore[arg-type]
            max_px=cfg.platform_max_px,
            enabled=cfg.platform_enabled,
            seed=s + 0,
            fps=cfg.fps,
        )

        # --- Atmosphere (applied on viewport after crop) ---
        self.atmosphere = AtmosphereEffect(
            condition=cfg.atm_condition,     # type: ignore[arg-type]
            strength=cfg.atm_strength,
            enabled=cfg.atm_enabled,
            seed=s + 10,
        )

        # --- Turbulence (applied on viewport after atmosphere) ---
        self.turbulence = TurbulenceEffect(
            wander_max_px=cfg.turbulence_wander_px,
            scintillation_sigma=cfg.turbulence_scint_sigma,
            blur_sigma=cfg.turbulence_blur_sigma,
            enabled=cfg.turbulence_enabled,
            seed=s + 20,
        )

        # --- Camera jitter (applied on viewport) ---
        self.jitter = CameraJitter(
            max_px=cfg.jitter_max_px,
            enabled=cfg.jitter_enabled,
            seed=s + 30,
        )

        # --- Image noise (applied last on viewport) ---
        self.salt_pepper = SaltPepperNoise(
            density=cfg.sp_density,
            enabled=cfg.sp_enabled,
            seed=s + 40,
        )
        self.gaussian = GaussianNoise(
            sigma=cfg.gauss_sigma,
            enabled=cfg.gauss_enabled,
            seed=s + 50,
        )
        self.poisson = PoissonNoise(
            gain=cfg.poisson_gain,
            enabled=cfg.poisson_enabled,
            seed=s + 60,
        )

        # --- Vibration / wind state ---
        self._t: float = 0.0
        self._wind_rng = np.random.default_rng(s + 70)
        self._wind: tuple[float, float] = (0.0, 0.0)
        #: Total image translation (px) applied by the last apply_viewport call:
        #: vibration + turbulence wander + camera jitter. Published to the telemetry HUD
        #: so the 3D view can show the true optical-axis disturbance.
        self.last_shift_px: tuple[float, float] = (0.0, 0.0)

    # ------------------------------------------------------------------
    # Stage 1: Full-scene disturbances (before camera crop)
    # ------------------------------------------------------------------

    def apply_full_scene(self, img: np.ndarray, dt: float) -> np.ndarray:
        """
        Apply platform motion to the full 2000x2000 scene image.
        Called by SimulatedSource before the camera crops its viewport.

        Args:
            img : Full-scene uint8 grayscale image.
            dt  : Time step in seconds (= 1/fps).

        Returns:
            Distorted uint8 image, same shape.
        """
        img = self.platform.apply(img, dt)
        return img

    # ------------------------------------------------------------------
    # Stage 2: Viewport disturbances (after camera crop)
    # ------------------------------------------------------------------

    def apply_viewport(
        self,
        img: np.ndarray,
        frame_idx: int | None = None,
        timestamp_s: float | None = None,
        **kwargs,
    ) -> np.ndarray:

        """
        Apply atmosphere → turbulence → jitter → noise to the 640x480 viewport.
        Called by the pipeline after VirtualCamera.render().

        Args:
            img : Viewport uint8 grayscale image (640x480).

        Returns:
            Distorted uint8 image, same shape.
        """
        # Mechanical vibration: deterministic sinusoid at vibration_hz (models
        # reaction wheels / cooling pumps — correlated across frames, unlike jitter).
        vib_dx = 0.0
        vib_dy = 0.0
        if self.cfg.vibration_px > 0.0:
            if timestamp_s is None:
                self._t += 1.0 / max(1.0, self.cfg.fps)
                t_v = self._t
            else:
                t_v = float(timestamp_s)
                self._t = t_v
            w = 2.0 * math.pi * self.cfg.vibration_hz
            dx = self.cfg.vibration_px * math.sin(w * t_v)
            dy = 0.7 * self.cfg.vibration_px * math.sin(w * 1.31 * t_v + 1.1)
            vib_dx, vib_dy = dx, dy
            M = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy]], dtype=np.float32)
            H, W = img.shape[:2]
            img = cv2.warpAffine(img, M, (W, H),
                                 flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=0)

        img = self.atmosphere.apply(img)
        img = self.turbulence.apply(img)
        img = self.jitter.apply(img)
        img = self.salt_pepper.apply(img)
        img = self.gaussian.apply(img)
        img = self.poisson.apply(img)

        # Total attitude translation applied to this frame (for the telemetry HUD).
        jx, jy = self.jitter.last_shift
        tx, ty = self.turbulence.last_wander
        self.last_shift_px = (vib_dx + tx + jx, vib_dy + ty + jy)
        return img

    def wind_rates(self, dt: float) -> tuple[float, float]:
        """Ornstein–Uhlenbeck rate disturbance (deg/s) on the gimbal axes.
        Returns (d_pan, d_tilt); both are 0 when wind_deg_s == 0."""
        sigma = self.cfg.wind_deg_s
        if sigma <= 0.0:
            if self._wind != (0.0, 0.0):
                self._wind = (0.0, 0.0)
            return self._wind
        tau = 0.5  # s — wind correlation time
        decay = math.exp(-dt / tau)
        kick = sigma * math.sqrt(max(1e-6, dt)) * 1.6
        wx = decay * self._wind[0] + float(self._wind_rng.normal(0.0, kick))
        wy = decay * self._wind[1] + float(self._wind_rng.normal(0.0, kick))
        # Clamp to ±4σ so a rare draw cannot slam the gimbal
        lim = 4.0 * sigma
        self._wind = (float(np.clip(wx, -lim, lim)), float(np.clip(wy, -lim, lim)))
        return self._wind

    # ------------------------------------------------------------------
    # Reset (used by SimulatedSource.reset())
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset stateful disturbances (platform motion drift, vibration phase, wind)."""
        self.platform.reset()
        self._t = 0.0
        self._wind = (0.0, 0.0)

    @property
    def noise(self) -> _NoiseProxy:
        return _NoiseProxy(self)


class _NoiseProxy:
    """Helper facade for backward compatibility and intuitive noise controls."""
    def __init__(self, parent: DisturbanceEngine) -> None:
        self._parent = parent

    def enable_salt_pepper(self, density: float = 0.08) -> None:
        self._parent.salt_pepper.enabled = True
        self._parent.salt_pepper.density = density

    def disable_salt_pepper(self) -> None:
        self._parent.salt_pepper.enabled = False

    def enable_gaussian(self, sigma: float = 15.0) -> None:
        self._parent.gaussian.enabled = True
        self._parent.gaussian.sigma = sigma

    def disable_gaussian(self) -> None:
        self._parent.gaussian.enabled = False
