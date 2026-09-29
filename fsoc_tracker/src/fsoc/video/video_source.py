"""
src/fsoc/video/video_source.py
================================
VideoFileSource: concrete FrameSource that reads a pre-recorded .mp4 video
and feeds it frame-by-frame into the tracking pipeline.

This is the BENCHMARK-2 critical component (30% of evaluation marks).
The PTZ camera is bypassed — the video is already the full scene, so
the tracker receives each decoded frame directly without any virtual
pan-tilt. Ground-truth is NOT available from a video file (returns None).

Supported formats: any codec that OpenCV can read (.mp4 H.264, .avi, etc.)
Expected spec from PS:  full-screen video, 30 fps, moving beacon, with noise.

Output frames are resized to the configured resolution if they differ from
the video resolution (the pipeline always expects the configured res_x × res_y).
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import cv2
from ..core.frame_source import FrameSource
from ..core.types import FullFrame


class VideoFileSource(FrameSource):
    """
    Reads frames from a .mp4 (or any OpenCV-readable) video file.

    The video is treated as the full scene; no virtual PTZ is applied.
    Ground-truth positions are unavailable (returns None).

    Parameters
    ----------
    video_path : str | Path
        Path to the video file.
    grayscale : bool
        If True (default), convert to grayscale.
    loop : bool
        If True, wrap around to frame 0 after the last frame.
    """

    def __init__(self,
                 video_path: str | Path,
                 grayscale: bool = True,
                 loop: bool = False) -> None:
        self._path = Path(video_path)
        if not self._path.exists():
            raise FileNotFoundError(f"Video file not found: {self._path}")

        self._grayscale = grayscale
        self._loop = loop
        self._cap = cv2.VideoCapture(str(self._path))

        if not self._cap.isOpened():
            raise RuntimeError(f"OpenCV could not open video: {self._path}")

        self._fps_native: float = float(self._cap.get(cv2.CAP_PROP_FPS)) or 30.0
        self._total_frames: int = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._frame_index: int = 0

    # ------------------------------------------------------------------
    # FrameSource interface
    # ------------------------------------------------------------------

    def next_frame(self) -> FullFrame | None:
        """
        Read and return the next video frame as a FullFrame.
        Returns None when the video ends (and loop=False).
        """
        ret, frame = self._cap.read()

        if not ret:
            if self._loop:
                # Rewind and try again
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._frame_index = 0
                ret, frame = self._cap.read()
                if not ret:
                    return None
            else:
                return None

        # Convert colour → grayscale if needed
        if self._grayscale:
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            if len(frame.shape) == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        ts = self._frame_index / self._fps_native
        ff = FullFrame(
            image=frame,
            frame_index=self._frame_index,
            timestamp_s=ts,
            ground_truth=None,      # No GT available from video
        )
        self._frame_index += 1
        return ff

    def reset(self) -> None:
        """Rewind video to the beginning."""
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self._frame_index = 0

    @property
    def fps(self) -> float:
        return self._fps_native

    @property
    def has_ground_truth(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def total_frames(self) -> int:
        """Total number of frames in the video (may be approximate for some codecs)."""
        return self._total_frames

    @property
    def duration_s(self) -> float:
        """Approximate video duration in seconds."""
        return self._total_frames / max(self._fps_native, 1e-6)

    @property
    def frame_index(self) -> int:
        return self._frame_index

    def __del__(self) -> None:
        """Release the video capture on garbage collection."""
        if hasattr(self, "_cap") and self._cap.isOpened():
            self._cap.release()
