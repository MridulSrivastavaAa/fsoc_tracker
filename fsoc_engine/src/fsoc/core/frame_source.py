"""
src/fsoc/core/frame_source.py
=============================
Abstract FrameSource interface.
All code in the pipeline ONLY knows about FrameSource — it never
knows whether the underlying data comes from the simulator or a .mp4 file.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from .types import FullFrame


class FrameSource(ABC):
    """
    Abstract base for all frame providers.
    Concrete implementations:
      - SimulatedSource  (simulation/)
      - VideoFileSource  (video/)
    """

    @abstractmethod
    def next_frame(self) -> FullFrame | None:
        """
        Return the next FullFrame, or None when the source is exhausted.
        The caller must check for None and stop the pipeline loop.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset to the first frame (rewind). No-op for infinite simulators."""
        ...

    @property
    @abstractmethod
    def fps(self) -> float:
        """Frames per second of this source."""
        ...

    @property
    @abstractmethod
    def has_ground_truth(self) -> bool:
        """True if this source supplies beacon ground-truth positions."""
        ...
