"""
Media processing pipeline for WebRTC: compositing, filters, overlays.

Provides:
- ``VideoFrameTransformer`` — base class for frame processors
- ``VideoCompositor`` — composite multiple tracks into a grid layout
- ``FrameOverlay`` — overlay text, timestamps, or images on video
- ``MediaPipeline`` — chain multiple transformers together
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ---------------------------------------------------------------------------
# Frame Transformer Base
# ---------------------------------------------------------------------------


class VideoFrameTransformer:
    """Base class for video frame transformation.

    Subclasses implement ``transform()`` which receives an aiortc
    ``VideoFrame`` and returns a modified ``VideoFrame``.

    Usage::

        class Grayscale(VideoFrameTransformer):
            def transform(self, frame):
                img = frame.to_ndarray(format="bgr24")
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                gray_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                return frame.from_ndarray(gray_bgr, format="bgr24")

        pipeline = MediaPipeline()
        pipeline.add(Grayscale())
        track = pipeline.wrap(original_track)
    """

    def transform(self, frame: Any) -> Any:
        """Transform a video frame.

        Args:
            frame: An aiortc ``VideoFrame``.

        Returns:
            A modified ``VideoFrame``.
        """
        raise NotImplementedError

    async def atransform(self, frame: Any) -> Any:
        """Async version of ``transform()``.

        Default implementation calls ``transform()`` synchronously.
        Override for async operations (e.g. network calls).
        """
        return self.transform(frame)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


# ---------------------------------------------------------------------------
# Built-in transformers
# ---------------------------------------------------------------------------


class GrayscaleTransformer(VideoFrameTransformer):
    """Convert video to grayscale (BGR output)."""

    def transform(self, frame: Any) -> Any:
        if not _HAS_CV2:
            raise RuntimeError("opencv-python required for GrayscaleTransformer")
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        return frame.from_ndarray(gray_bgr, format="bgr24")


class MirrorTransformer(VideoFrameTransformer):
    """Mirror video horizontally."""

    def __init__(self, flip_code: int = 1):
        self.flip_code = flip_code

    def transform(self, frame: Any) -> Any:
        if not _HAS_CV2:
            raise RuntimeError("opencv-python required for MirrorTransformer")
        img = frame.to_ndarray(format="bgr24")
        flipped = cv2.flip(img, self.flip_code)
        return frame.from_ndarray(flipped, format="bgr24")


class ResizeTransformer(VideoFrameTransformer):
    """Resize video frames to a target size."""

    def __init__(self, width: int, height: int, interpolation: int | None = None):
        self.width = width
        self.height = height
        self.interpolation = interpolation or (
            cv2.INTER_LINEAR if _HAS_CV2 else None
        )

    def transform(self, frame: Any) -> Any:
        if not _HAS_CV2:
            raise RuntimeError("opencv-python required for ResizeTransformer")
        img = frame.to_ndarray(format="bgr24")
        resized = cv2.resize(img, (self.width, self.height), interpolation=self.interpolation)
        return frame.from_ndarray(resized, format="bgr24")


class RotationTransformer(VideoFrameTransformer):
    """Rotate video frames by a given angle."""

    def __init__(self, angle: float = 90.0):
        self.angle = angle

    def transform(self, frame: Any) -> Any:
        if not _HAS_CV2:
            raise RuntimeError("opencv-python required for RotationTransformer")
        img = frame.to_ndarray(format="bgr24")
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, self.angle, 1.0)
        rotated = cv2.warpAffine(img, matrix, (w, h))
        return frame.from_ndarray(rotated, format="bgr24")


class FrameOverlay(VideoFrameTransformer):
    """Overlay text or timestamp on video frames.

    Usage::

        overlay = FrameOverlay(text="Hello", position=(10, 30),
                               color=(255, 255, 255), font_scale=1.0)
        pipeline.add(overlay)

    Can also show a live timestamp::

        overlay = FrameOverlay.timestamp(position=(10, 30))
    """

    def __init__(
        self,
        text: str = "",
        position: tuple[int, int] = (10, 30),
        color: tuple[int, int, int] = (255, 255, 255),
        font_scale: float = 1.0,
        thickness: int = 2,
        show_timestamp: bool = False,
    ):
        self.text = text
        self.position = position
        self.color = color
        self.font_scale = font_scale
        self.thickness = thickness
        self.show_timestamp = show_timestamp

    @classmethod
    def timestamp(
        cls,
        position: tuple[int, int] = (10, 30),
        color: tuple[int, int, int] = (255, 255, 255),
    ) -> FrameOverlay:
        """Create an overlay that shows a live timestamp."""
        return cls(position=position, color=color, show_timestamp=True)

    def transform(self, frame: Any) -> Any:
        if not _HAS_CV2:
            raise RuntimeError("opencv-python required for FrameOverlay")
        img = frame.to_ndarray(format="bgr24")

        display_text = self.text
        if self.show_timestamp:
            display_text = time.strftime("%Y-%m-%d %H:%M:%S")

        if display_text:
            cv2.putText(
                img,
                display_text,
                self.position,
                cv2.FONT_HERSHEY_SIMPLEX,
                self.font_scale,
                self.color,
                self.thickness,
                cv2.LINE_AA,
            )

        return frame.from_ndarray(img, format="bgr24")


# ---------------------------------------------------------------------------
# Video Compositor (grid layout)
# ---------------------------------------------------------------------------


class VideoCompositor(VideoFrameTransformer):
    """Composite multiple video tracks into a grid layout.

    Combines N incoming video tracks into a single output frame
    arranged in a grid (2x2, 3x3, etc.).

    Usage::

        compositor = VideoCompositor(columns=2)
        track = compositor.composite(frame1, frame2, frame3, frame4)
    """

    def __init__(self, columns: int = 2, target_width: int = 1280, target_height: int = 720):
        self.columns = columns
        self.target_width = target_width
        self.target_height = target_height

    def composite(self, *frames: Any) -> Any:
        """Composite multiple frames into one grid frame.

        Args:
            *frames: ``VideoFrame`` objects to arrange in a grid.

        Returns:
            A single ``VideoFrame`` with the grid composite.
        """
        if not _HAS_CV2:
            raise RuntimeError("opencv-python required for VideoCompositor")
        if not frames:
            raise ValueError("at least one frame required")

        n = len(frames)
        rows = (n + self.columns - 1) // self.columns
        cell_w = self.target_width // self.columns
        cell_h = self.target_height // rows

        canvas = np.zeros((self.target_height, self.target_width, 3), dtype=np.uint8)

        for i, frame in enumerate(frames):
            row = i // self.columns
            col = i % self.columns

            img = frame.to_ndarray(format="bgr24")
            resized = cv2.resize(img, (cell_w, cell_h))

            y_start = row * cell_h
            y_end = y_start + cell_h
            x_start = col * cell_w
            x_end = x_start + cell_w

            canvas[y_start:y_end, x_start:x_end] = resized

        return frames[0].from_ndarray(canvas, format="bgr24")


# ---------------------------------------------------------------------------
# Media Pipeline
# ---------------------------------------------------------------------------


class MediaPipeline:
    """Chain multiple ``VideoFrameTransformer`` instances.

    Each transformer is applied sequentially to every frame passing
    through the pipeline.

    Usage::

        pipeline = MediaPipeline()
        pipeline.add(MirrorTransformer())
        pipeline.add(FrameOverlay.timestamp())
        pipeline.add(ResizeTransformer(640, 480))

        # Wrap an aiortc track
        wrapped_track = pipeline.wrap(original_track)

    Extensibility:
        Subclass and override ``on_frame()`` to add global
        pre/post processing.
    """

    def __init__(self):
        self._transformers: list[VideoFrameTransformer] = []

    def add(self, transformer: VideoFrameTransformer) -> None:
        """Add a transformer to the end of the pipeline."""
        self._transformers.append(transformer)

    def remove(self, transformer: VideoFrameTransformer) -> None:
        """Remove a transformer from the pipeline."""
        self._transformers.remove(transformer)

    def clear(self) -> None:
        """Remove all transformers."""
        self._transformers.clear()

    def wrap(self, source_track: Any) -> Any:
        """Wrap an aiortc ``MediaStreamTrack`` with the pipeline.

        Returns a new track proxy that applies all transformers
        to each frame.
        """
        from aiortc import MediaStreamTrack

        class _PipelineTrack(MediaStreamTrack):
            kind = source_track.kind

            def __init__(self, pipeline: MediaPipeline, source: Any):
                super().__init__()
                self._pipeline = pipeline
                self._source = source

            async def recv(self) -> Any:
                frame = await self._source.recv()
                frame = await self._pipeline._on_frame(frame)
                for t in self._pipeline._transformers:
                    frame = await t.atransform(frame)
                return frame

        return _PipelineTrack(self, source_track)

    async def _on_frame(self, frame: Any) -> Any:
        """Pre-processing hook before transformers.

        Override for global frame processing (e.g. logging, metrics).
        """
        return frame

    @property
    def transformers(self) -> list[VideoFrameTransformer]:
        """Read-only list of registered transformers."""
        return list(self._transformers)

    def __len__(self) -> int:
        return len(self._transformers)

    def __repr__(self) -> str:
        return f"MediaPipeline({self._transformers})"


__all__ = [
    "VideoFrameTransformer",
    "MediaPipeline",
    "VideoCompositor",
    "FrameOverlay",
    "GrayscaleTransformer",
    "MirrorTransformer",
    "ResizeTransformer",
    "RotationTransformer",
]
