"""
src/fsoc/tracking/particle_filter.py
===================================
Lightweight 2D Particle Filter for Autonomous Target Recovery and Reacquisition (Step 4).

Features:
- 4D state vector: [x, y, vx, vy]
- Vectorized NumPy particle propagation and candidate proximity weighting
- Systematic low-variance stratified resampling with anti-degeneracy roughening
- Cluster dispersion and multi-frame spatial consistency verification
- Zero-overhead when inactive (normal steady-state TRACK mode)
"""
from __future__ import annotations
import math
from typing import Optional, List, Tuple
import numpy as np

from ..core.types import Detection, TrackState
from ..core.config import ParticleFilterConfig, AppConfig


class ParticleFilter:
    """
    Lightweight 2D Particle Filter for beacon reacquisition and recovery.
    Operates as an auxiliary recovery mechanism during signal loss / occlusion.
    """
    def __init__(
        self,
        cfg: ParticleFilterConfig | AppConfig | None = None,
        dt: float = 1.0 / 30.0,
        viewport_w: float = 640.0,
        viewport_h: float = 480.0,
        seed: Optional[int] = None,
    ) -> None:
        if cfg is None:
            p_cfg = ParticleFilterConfig()
        elif isinstance(cfg, AppConfig):
            p_cfg = cfg.tracking.particle_filter
            dt = cfg.pipeline.dt
        elif isinstance(cfg, ParticleFilterConfig):
            p_cfg = cfg
        else:
            raise TypeError(f"Unsupported config type: {type(cfg)}")

        self.cfg = p_cfg
        self.dt = float(dt)
        self.vw = float(viewport_w)
        self.vh = float(viewport_h)
        self.rng = np.random.RandomState(seed)

        self.N = int(self.cfg.num_particles)
        self.particles = np.zeros((self.N, 4), dtype=np.float64)  # [x, y, vx, vy]
        self.weights = np.ones(self.N, dtype=np.float64) / self.N

        self.is_active: bool = False
        self.confirm_count: int = 0
        self.active_frames: int = 0
        self.last_cluster_std: float = 0.0
        self.last_n_eff: float = float(self.N)

    def reset(self) -> None:
        """Deactivate filter and clear particle state."""
        self.is_active = False
        self.confirm_count = 0
        self.active_frames = 0
        self.particles.fill(0.0)
        self.weights.fill(1.0 / self.N)
        self.last_cluster_std = 0.0
        self.last_n_eff = float(self.N)

    def initialize(
        self,
        center_x: float,
        center_y: float,
        vx: float = 0.0,
        vy: float = 0.0,
        pos_std: Optional[float] = None,
        vel_std: Optional[float] = None,
    ) -> None:
        """
        Initialize particle cloud centered on last reliable predicted state.

        Args:
            center_x: Last known / predicted X position (viewport px).
            center_y: Last known / predicted Y position (viewport px).
            vx: Last known / predicted velocity X (px/s).
            vy: Last known / predicted velocity Y (px/s).
            pos_std: Spatial standard deviation for particle scatter (px).
            vel_std: Velocity standard deviation for particle scatter (px/s).
        """
        p_std = float(pos_std if pos_std is not None else self.cfg.init_pos_std_px)
        v_std = float(vel_std if vel_std is not None else self.cfg.init_vel_std_px_s)

        self.particles[:, 0] = self.rng.normal(center_x, p_std, self.N)
        self.particles[:, 1] = self.rng.normal(center_y, p_std, self.N)
        self.particles[:, 2] = self.rng.normal(vx, v_std, self.N)
        self.particles[:, 3] = self.rng.normal(vy, v_std, self.N)

        # Clip spatial bounds to viewport
        self.particles[:, 0] = np.clip(self.particles[:, 0], 0.0, self.vw)
        self.particles[:, 1] = np.clip(self.particles[:, 1], 0.0, self.vh)

        self.weights.fill(1.0 / self.N)
        self.is_active = True
        self.confirm_count = 0
        self.active_frames = 0
        self.last_cluster_std = p_std
        self.last_n_eff = float(self.N)

    def predict(self) -> None:
        """
        Propagate all particles forward in time via constant velocity + acceleration diffusion.
        """
        if not self.is_active:
            return

        self.active_frames += 1

        # Diffusion noise scales with active duration to expand search envelope during prolonged loss
        spread_scale = min(2.5, 1.0 + 0.1 * self.active_frames)
        pos_noise = self.cfg.process_pos_noise_std * spread_scale
        vel_noise = self.cfg.process_vel_noise_std * spread_scale

        # Propagate: x(t+1) = x(t) + v(t)*dt + noise
        self.particles[:, 0] += self.particles[:, 2] * self.dt + self.rng.normal(0.0, pos_noise, self.N)
        self.particles[:, 1] += self.particles[:, 3] * self.dt + self.rng.normal(0.0, pos_noise, self.N)
        self.particles[:, 2] += self.rng.normal(0.0, vel_noise, self.N)
        self.particles[:, 3] += self.rng.normal(0.0, vel_noise, self.N)

        # Soft bounce/clamp at boundaries
        self.particles[:, 0] = np.clip(self.particles[:, 0], 0.0, self.vw)
        self.particles[:, 1] = np.clip(self.particles[:, 1], 0.0, self.vh)

    def update(self, candidates: List[Detection]) -> Tuple[bool, TrackState]:
        """
        Evaluate candidate detections against particle distribution, update weights,
        perform systematic resampling if degenerate, and verify reacquisition.

        Args:
            candidates: List of detected beacon candidates from vision pipeline.

        Returns:
            (reacquired_flag, current_or_recovered_track_state)
        """
        if not self.is_active:
            return False, TrackState(x=0.0, y=0.0, vx=0.0, vy=0.0, confidence=0.0, locked=False)

        # 1. Particle Weighting based on candidate proximity and confidence
        valid_candidates = [
            c for c in candidates if c.score >= self.cfg.min_candidate_score
        ]

        if valid_candidates:
            # Gaussian observation likelihood across all valid candidates
            cand_xy = np.array([[c.x, c.y] for c in valid_candidates], dtype=np.float64)  # (K, 2)
            cand_scores = np.array([c.score for c in valid_candidates], dtype=np.float64)  # (K,)

            sigma2_2 = 2.0 * (self.cfg.meas_pos_sigma_px ** 2)

            # Compute pairwise squared Euclidean distances: (N, K)
            px = self.particles[:, 0:1]  # (N, 1)
            py = self.particles[:, 1:2]  # (N, 1)
            dx = px - cand_xy[:, 0]  # (N, K)
            dy = py - cand_xy[:, 1]  # (N, K)
            d2 = dx ** 2 + dy ** 2   # (N, K)

            # Likelihood contribution from all candidates: sum_k [score_k * exp(-d2/(2*sigma^2))]
            cand_liks = cand_scores * np.exp(-d2 / sigma2_2)  # (N, K)
            total_lik = np.sum(cand_liks, axis=1) + 1e-12     # (N,)

            self.weights *= total_lik
        else:
            # Full occlusion: decay weights towards uniform
            self.weights = 0.90 * self.weights + 0.10 * (1.0 / self.N)

        # Normalize weights safely
        w_sum = np.sum(self.weights)
        if w_sum > 1e-12:
            self.weights /= w_sum
        else:
            self.weights.fill(1.0 / self.N)

        # 2. Resampling Condition (Effective Sample Size N_eff)
        n_eff = 1.0 / max(1e-12, float(np.sum(np.square(self.weights))))
        self.last_n_eff = n_eff

        if n_eff < (self.cfg.resample_threshold_ratio * self.N):
            self._systematic_resample()

        # 3. Weighted State Estimate & Cluster Dispersion
        mean_x = float(np.sum(self.weights * self.particles[:, 0]))
        mean_y = float(np.sum(self.weights * self.particles[:, 1]))
        mean_vx = float(np.sum(self.weights * self.particles[:, 2]))
        mean_vy = float(np.sum(self.weights * self.particles[:, 3]))

        var_pos = float(
            np.sum(self.weights * ((self.particles[:, 0] - mean_x) ** 2 + (self.particles[:, 1] - mean_y) ** 2))
        )
        cluster_std = float(np.sqrt(max(0.0, var_pos)))
        self.last_cluster_std = cluster_std

        # 4. Multi-Frame Reacquisition Confirmation
        reacquired = False
        if valid_candidates:
            # Check if any candidate is within spatial tolerance of the particle mean
            cand_dists = [math.hypot(c.x - mean_x, c.y - mean_y) for c in valid_candidates]
            min_dist = min(cand_dists)
            best_cand = valid_candidates[int(np.argmin(cand_dists))]

            if min_dist <= (1.8 * self.cfg.meas_pos_sigma_px) and cluster_std <= self.cfg.reacquire_cluster_std_thresh:
                self.confirm_count += 1
            else:
                self.confirm_count = max(0, self.confirm_count - 1)

            if self.confirm_count >= self.cfg.reacquire_confirm_frames:
                # Confirmed reacquisition!
                reacquired = True
                # Use sub-pixel centroid of best candidate for exact hand-off
                mean_x = float(best_cand.x)
                mean_y = float(best_cand.y)
        else:
            self.confirm_count = 0

        # Confidence based on cluster compactness and confirmation progress
        conf = float(np.clip(
            (self.confirm_count / max(1, self.cfg.reacquire_confirm_frames)) *
            math.exp(-cluster_std / max(1.0, self.cfg.reacquire_cluster_std_thresh)),
            0.0,
            1.0,
        ))

        state = TrackState(
            x=mean_x,
            y=mean_y,
            vx=mean_vx,
            vy=mean_vy,
            confidence=conf,
            locked=reacquired,
            uncertainty=cluster_std,
            pf_active=True,
            pf_particles=self.N,
            pf_cluster_std=cluster_std,
            pf_n_eff=n_eff,
            pf_reacquired=reacquired,
        )

        return reacquired, state

    def _systematic_resample(self) -> None:
        """
        Deterministic low-variance systematic resampling in O(N).
        """
        positions = (self.rng.uniform(0.0, 1.0 / self.N) + np.arange(self.N) / self.N)
        indexes = np.zeros(self.N, dtype=np.int64)
        cumulative_sum = np.cumsum(self.weights)
        i, j = 0, 0
        while i < self.N:
            if positions[i] < cumulative_sum[j]:
                indexes[i] = j
                i += 1
            else:
                j += 1
                if j >= self.N:
                    indexes[i:] = self.N - 1
                    break

        self.particles = self.particles[indexes].copy()

        # Roughening jitter to prevent particle depletion
        self.particles[:, 0] += self.rng.normal(0.0, 0.6, self.N)
        self.particles[:, 1] += self.rng.normal(0.0, 0.6, self.N)
        self.particles[:, 2] += self.rng.normal(0.0, 1.5, self.N)
        self.particles[:, 3] += self.rng.normal(0.0, 1.5, self.N)

        self.particles[:, 0] = np.clip(self.particles[:, 0], 0.0, self.vw)
        self.particles[:, 1] = np.clip(self.particles[:, 1], 0.0, self.vh)

        self.weights.fill(1.0 / self.N)

    def get_state(self) -> TrackState:
        """Return current state estimate from particle cloud."""
        if not self.is_active:
            return TrackState(x=0.0, y=0.0, vx=0.0, vy=0.0, confidence=0.0, locked=False, pf_active=False)

        mean_x = float(np.sum(self.weights * self.particles[:, 0]))
        mean_y = float(np.sum(self.weights * self.particles[:, 1]))
        mean_vx = float(np.sum(self.weights * self.particles[:, 2]))
        mean_vy = float(np.sum(self.weights * self.particles[:, 3]))

        return TrackState(
            x=mean_x,
            y=mean_y,
            vx=mean_vx,
            vy=mean_vy,
            confidence=float(self.confirm_count / max(1, self.cfg.reacquire_confirm_frames)),
            locked=bool(self.confirm_count >= self.cfg.reacquire_confirm_frames),
            uncertainty=float(self.last_cluster_std),
            pf_active=True,
            pf_particles=self.N,
            pf_cluster_std=float(self.last_cluster_std),
            pf_n_eff=float(self.last_n_eff),
            pf_reacquired=bool(self.confirm_count >= self.cfg.reacquire_confirm_frames),
        )
