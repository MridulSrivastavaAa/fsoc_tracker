"""
src/fsoc/tracking/state_machine.py
==================================
5-State Autonomous Tracking Machine for FSOC Terminals.
States:
  SEARCH     &bull; Scanning wide scene or awaiting candidate detection
  ACQUIRE    &bull; Candidate spotted; verifying across N consecutive frames
  TRACK      &bull; High-confidence lock; active closed-loop PID control
  LOST       &bull; Signal dropout / cloud occlusion; coasting on Kalman velocity
  REACQUIRE  &bull; Autonomous recovery scan around last known trajectory

Enforces ISRO PS requirements:
- R13: Rapid target acquisition (&le; 2 s)
- R15: Target loss rate &lt; 5% with autonomous re-lock
"""
from __future__ import annotations
from enum import Enum
from typing import Optional

from ..core.config import TrackingConfig, AppConfig


class State(str, Enum):
    SEARCH = "SEARCH"
    ACQUIRE = "ACQUIRE"
    TRACK = "TRACK"
    LOST = "LOST"
    REACQUIRE = "REACQUIRE"


class TrackingStateMachine:
    """
    Autonomous tracking state coordinator.
    Tracks state transitions, lock durations, and acquisition timestamps.
    """
    def __init__(self, cfg: TrackingConfig | AppConfig | None = None) -> None:
        if cfg is None:
            t_cfg = TrackingConfig()
        elif isinstance(cfg, AppConfig):
            t_cfg = cfg.tracking
        elif isinstance(cfg, TrackingConfig):
            t_cfg = cfg
        else:
            raise TypeError(f"Unsupported config type: {type(cfg)}")

        self.cfg = t_cfg
        self.state: State = State.SEARCH

        # Time at which the current state started (mirrors the frontend
        # Supervisor.since) — used for the per-state elapsed time reported in the
        # snapshot as `stateSince`.
        self.since: float = 0.0

        # Consecutive frame counters
        self.detect_streak: int = 0
        self.miss_streak: int = 0
        self.reacquire_frames: int = 0

        # Timing metrics
        self.start_time_s: Optional[float] = None
        self.acquisition_time_s: Optional[float] = None
        self.state_enter_time_s: float = 0.0
        self.lost_enter_time_s: Optional[float] = None
        self.reacquisition_times: list[float] = []

        # Aggregate statistics
        self.frames_per_state: dict[str, int] = {s.value: 0 for s in State}
        self.transitions: list[tuple[float, str, str]] = []  # (t, from_state, to_state)

    def transition_to(self, new_state: State, timestamp_s: float) -> None:
        """Execute state transition and record event."""
        if new_state == self.state:
            return

        old_state_str = self.state.value
        new_state_str = new_state.value

        self.transitions.append((timestamp_s, old_state_str, new_state_str))
        self.state = new_state
        self.state_enter_time_s = timestamp_s
        # Time the current state started (mirrors the frontend Supervisor).since
        self.since = timestamp_s

        # Reset counters on state entry
        if new_state == State.ACQUIRE:
            self.detect_streak = 1
        elif new_state == State.TRACK:
            self.miss_streak = 0
            # If transitioning to TRACK for the first time, record acquisition time
            if self.acquisition_time_s is None and self.start_time_s is not None:
                self.acquisition_time_s = timestamp_s - self.start_time_s
            # If recovering from LOST / REACQUIRE, record reacquisition duration
            if self.lost_enter_time_s is not None:
                self.reacquisition_times.append(timestamp_s - self.lost_enter_time_s)
                self.lost_enter_time_s = None
        elif new_state == State.LOST:
            self.lost_enter_time_s = timestamp_s
        elif new_state == State.REACQUIRE:
            self.reacquire_frames = 0
        elif new_state == State.SEARCH:
            self.detect_streak = 0
            self.miss_streak = 0

    def step(self, detection_found: bool, timestamp_s: float) -> str:
        """
        Advance state machine by one simulation frame.
        
        Args:
            detection_found: True if a valid beacon detection candidate exists.
            timestamp_s: Current simulation timestamp.
            
        Returns:
            Current state name as string.
        """
        if self.start_time_s is None:
            self.start_time_s = timestamp_s
            self.state_enter_time_s = timestamp_s
            self.since = timestamp_s

        self.frames_per_state[self.state.value] += 1

        if detection_found:
            self.detect_streak += 1
            self.miss_streak = 0
        else:
            self.miss_streak += 1
            self.detect_streak = 0

        # State transition logic
        if self.state == State.SEARCH:
            if detection_found:
                self.transition_to(State.ACQUIRE, timestamp_s)

        elif self.state == State.ACQUIRE:
            if not detection_found:
                # Lost before lock confirmation
                self.transition_to(State.SEARCH, timestamp_s)
            elif self.detect_streak >= self.cfg.consecutive_acquire_frames:
                # Confirmed lock!
                self.transition_to(State.TRACK, timestamp_s)

        elif self.state == State.TRACK:
            if self.miss_streak >= self.cfg.consecutive_lost_frames:
                # Target dropped
                self.transition_to(State.LOST, timestamp_s)

        elif self.state == State.LOST:
            if detection_found:
                # Recovered immediately
                self.transition_to(State.TRACK, timestamp_s)
            elif self.miss_streak >= self.cfg.consecutive_lost_frames + self.cfg.max_coast_frames:
                # Coasting limit exceeded; trigger active re-acquisition
                self.transition_to(State.REACQUIRE, timestamp_s)

        elif self.state == State.REACQUIRE:
            self.reacquire_frames += 1
            if detection_found:
                self.transition_to(State.ACQUIRE, timestamp_s)
            elif self.reacquire_frames >= self.cfg.reacquire_timeout_frames:
                # Reacquisition timeout; fall back to wide SEARCH
                self.transition_to(State.SEARCH, timestamp_s)

        return self.state.value

    @property
    def is_locked(self) -> bool:
        """True if in steady-state TRACK mode."""
        return self.state == State.TRACK

    @property
    def lock_retention_pct(self) -> float:
        """Percentage of total simulation time spent in TRACK state."""
        total = sum(self.frames_per_state.values())
        if total == 0:
            return 0.0
        return float(100.0 * self.frames_per_state[State.TRACK.value] / total)

    @property
    def target_loss_pct(self) -> float:
        """Percentage of simulation time spent in LOST or REACQUIRE states."""
        total = sum(self.frames_per_state.values())
        if total == 0:
            return 0.0
        lost_frames = self.frames_per_state[State.LOST.value] + self.frames_per_state[State.REACQUIRE.value]
        return float(100.0 * lost_frames / total)

    def reset(self) -> None:
        """Reset state machine."""
        self.state = State.SEARCH
        self.detect_streak = 0
        self.miss_streak = 0
        self.reacquire_frames = 0
        self.start_time_s = None
        self.acquisition_time_s = None
        self.state_enter_time_s = 0.0
        self.lost_enter_time_s = None
        self.reacquisition_times.clear()
        self.transitions.clear()
        self.frames_per_state = {s.value: 0 for s in State}
