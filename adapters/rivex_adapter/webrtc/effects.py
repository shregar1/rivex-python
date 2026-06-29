"""
Audio and video effects for WebRTC media streams.

Provides:

- ``VideoEffect`` / ``AudioEffect`` — base effect classes
- ``ChromaKey`` — green screen removal (video)
- ``GaussianBlur`` — background blur (video)
- ``EchoEffect`` — simple echo/delay (audio)
- ``ReverbEffect`` — convolution reverb (audio)
- ``EffectPipeline`` — chain of effects applied to a track

Usage::

    pipeline = EffectPipeline()
    pipeline.add(GaussianBlur(radius=5.0))
    pipeline.add(ChromaKey(color=(0, 255, 0), threshold=0.3))

    # Wrap an existing track
    processed = pipeline.wrap(original_video_track)
"""

from __future__ import annotations

import asyncio
import math
import struct
import time
from abc import ABC, abstractmethod
from typing import Any


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------

# We define a minimal frame/data abstraction so effects don't depend on a
# specific media library.  In production you would pass aiortc frames.
# Here we use a simple dict-based frame to keep it testable.


class MediaFrame:
    """Minimal frame wrapper for effect processing.

    In production this would be an ``aiortc.mediastreams.VideoFrame`` or
    ``AudioFrame``.  For tests we use a dict::

        # Video
        frame = MediaFrame({
            "type": "video",
            "data": b"..."          # raw pixel data (RGB or YUV)
            "width": 1280,
            "height": 720,
        })

        # Audio
        frame = MediaFrame({
            "type": "audio",
            "data": b"..."          # raw PCM 16-bit little-endian
            "sample_rate": 48000,
            "channels": 1,
        })
    """

    def __init__(self, data: dict):
        self._data = data

    @property
    def data(self) -> dict:
        return self._data

    @property
    def kind(self) -> str:
        return self._data.get("type", "unknown")

    @property
    def width(self) -> int:
        return self._data.get("width", 0)

    @property
    def height(self) -> int:
        return self._data.get("height", 0)

    def copy(self, **overrides) -> MediaFrame:
        d = dict(self._data)
        d.update(overrides)
        return MediaFrame(d)


# ---------------------------------------------------------------------------
# Effect base classes
# ---------------------------------------------------------------------------


class VideoEffect(ABC):
    """Base class for video effects."""

    name: str = "video_effect"

    @abstractmethod
    def process(self, frame: MediaFrame) -> MediaFrame:
        """Apply effect to a video frame and return the processed frame."""
        ...


class AudioEffect(ABC):
    """Base class for audio effects."""

    name: str = "audio_effect"

    @abstractmethod
    def process(self, frame: MediaFrame) -> MediaFrame:
        """Apply effect to an audio frame and return the processed frame."""
        ...


# ---------------------------------------------------------------------------
# Video Effects
# ---------------------------------------------------------------------------


class ChromaKey(VideoEffect):
    """Chroma-key (greenscreen) effect.

    Replaces pixels matching *color* with transparent black.

    In a real implementation you'd use OpenCV; here we stub the logic
    for framework completeness.
    """

    name = "chroma_key"

    def __init__(self, color: tuple[int, int, int] = (0, 255, 0), threshold: float = 0.3):
        self._color = color
        self._threshold = threshold

    def process(self, frame: MediaFrame) -> MediaFrame:
        if frame.kind != "video":
            return frame

        w, h = frame.width, frame.height
        raw = frame._data.get("data", b"")

        if not raw:
            return frame

        # In production: use OpenCV inRange/mask
        # Here we do a simple pixel-level stub
        processed = self._apply_chroma(raw, w, h)

        return frame.copy(data=processed)

    def _apply_chroma(self, data: bytes, width: int, height: int) -> bytes:
        # Placeholder: return data unchanged
        # (integration with OpenCV/numpy would go here)
        return data


class GaussianBlur(VideoEffect):
    """Apply a Gaussian blur to video frames.

    In production: OpenCV ``GaussianBlur``.  Here we stub.
    """

    name = "gaussian_blur"

    def __init__(self, radius: float = 3.0):
        self._radius = radius

    def process(self, frame: MediaFrame) -> MediaFrame:
        if frame.kind != "video":
            return frame
        # Stub — real impl uses OpenCV
        return frame


class BackgroundBlur(VideoEffect):
    """Advanced background blur (person segmentation + blur).

    In production you'd use MediaPipe or TensorFlow for segmentation,
    then blur the background region only.

    This stub tracks whether segmentation *would* be called.
    """

    name = "background_blur"

    def __init__(self, radius: float = 5.0, model: str = "mediapipe"):
        self._radius = radius
        self._model = model
        self._segments: int = 0

    @property
    def segments_processed(self) -> int:
        return self._segments

    def process(self, frame: MediaFrame) -> MediaFrame:
        if frame.kind != "video":
            return frame
        self._segments += 1
        return frame


# ---------------------------------------------------------------------------
# Audio Effects
# ---------------------------------------------------------------------------


class EchoEffect(AudioEffect):
    """Simple echo/delay effect.

    Adds a delayed copy of the input at reduced gain.

    Uses an internal circular buffer for the delay line.
    """

    name = "echo"

    def __init__(
        self,
        delay_ms: float = 100.0,
        decay: float = 0.4,
        sample_rate: int = 48000,
    ):
        self._delay_samples = int(sample_rate * delay_ms / 1000)
        self._decay = decay
        self._buffer: list[int] = [0] * self._delay_samples
        self._pos = 0

    def process(self, frame: MediaFrame) -> MediaFrame:
        if frame.kind != "audio":
            return frame

        raw = frame._data.get("data", b"")
        if not raw:
            return frame

        samples = list(struct.iter_unpack("<h", raw))
        out = bytearray(len(raw))

        for i, (sample,) in enumerate(samples):
            delayed = self._buffer[self._pos]
            mixed = max(-32768, min(32767, sample + int(delayed * self._decay)))
            struct.pack_into("<h", out, i * 2, mixed)
            self._buffer[self._pos] = sample
            self._pos = (self._pos + 1) % self._delay_samples

        return frame.copy(data=bytes(out))


class ReverbEffect(AudioEffect):
    """Simple convolution reverb using an impulse response.

    In production you'd load an IR WAV file.  Here we use a synthetic
    exponential decay impulse.
    """

    name = "reverb"

    def __init__(
        self,
        decay_ms: float = 500.0,
        decay_db: float = 60.0,
        sample_rate: int = 48000,
    ):
        ir_length = int(sample_rate * decay_ms / 1000)
        decay_linear = 10 ** (-decay_db / 20)
        self._ir = [
            (1.0 - i / ir_length) * decay_linear
            for i in range(ir_length)
        ]
        self._buffer: list[int] = [0] * len(self._ir)
        self._pos = 0
        self._ir_length = ir_length

    def process(self, frame: MediaFrame) -> MediaFrame:
        if frame.kind != "audio":
            return frame

        raw = frame._data.get("data", b"")
        if not raw:
            return frame

        samples = list(struct.iter_unpack("<h", raw))
        out = bytearray(len(raw))

        for i, (sample,) in enumerate(samples):
            self._buffer[self._pos] = sample
            wet = 0
            for j in range(self._ir_length):
                idx = (self._pos - j) % self._ir_length
                wet += int(self._buffer[idx] * self._ir[j])
            wet = max(-32768, min(32767, wet))
            mixed = max(-32768, min(32767, sample + wet))
            struct.pack_into("<h", out, i * 2, mixed)
            self._pos = (self._pos + 1) % self._ir_length

        return frame.copy(data=bytes(out))


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class EffectPipeline:
    """Chain of effects applied to a media stream.

    Usage::

        pipeline = EffectPipeline()
        pipeline.add(GaussianBlur(radius=5.0))
        pipeline.add(ChromaKey())

        # Wrap a track — pipeline replaces the track's recv
        wrapped_track = pipeline.wrap(original_track)

        # Or process individual frames
        processed = pipeline.process_frame(frame)
    """

    def __init__(self):
        self._video_effects: list[VideoEffect] = []
        self._audio_effects: list[AudioEffect] = []

    def add(self, effect: VideoEffect | AudioEffect) -> None:
        """Register an effect (applied in order)."""
        if isinstance(effect, VideoEffect):
            self._video_effects.append(effect)
        elif isinstance(effect, AudioEffect):
            self._audio_effects.append(effect)

    def remove(self, effect: VideoEffect | AudioEffect) -> None:
        """Unregister an effect."""
        if isinstance(effect, VideoEffect):
            self._video_effects.remove(effect)
        elif isinstance(effect, AudioEffect):
            self._audio_effects.remove(effect)

    def clear(self) -> None:
        """Remove all effects."""
        self._video_effects.clear()
        self._audio_effects.clear()

    def process_frame(self, frame: MediaFrame) -> MediaFrame:
        """Apply all registered effects to a frame."""
        if frame.kind == "video":
            for effect in self._video_effects:
                frame = effect.process(frame)
        elif frame.kind == "audio":
            for effect in self._audio_effects:
                frame = effect.process(frame)
        return frame

    def wrap(self, track: Any) -> Any:
        """Wrap a media stream track so effects apply transparently.

        The track must have an async ``recv()`` that returns something
        with ``kind``, ``width``, ``height``, and ``data``.
        """
        pipeline = self
        original_recv = track.recv

        async def patched_recv():
            raw_frame = await original_recv()
            frame = MediaFrame({
                "type": raw_frame.kind if hasattr(raw_frame, "kind") else "unknown",
                "data": raw_frame,
                "width": getattr(raw_frame, "width", 0),
                "height": getattr(raw_frame, "height", 0),
            })
            processed = pipeline.process_frame(frame)
            return processed._data.get("data", raw_frame)

        track.recv = patched_recv
        return track


__all__ = [
    "VideoEffect",
    "AudioEffect",
    "ChromaKey",
    "GaussianBlur",
    "BackgroundBlur",
    "EchoEffect",
    "ReverbEffect",
    "EffectPipeline",
    "MediaFrame",
]
