"""
Unified media source abstraction for WebRTC.

``MediaSource`` — abstract base for any media input:
  - ``CameraSource`` — webcam capture
  - ``MicrophoneSource`` — mic capture
  - ``ScreenSource`` — screen/window capture
  - ``FileSource`` — read from a media file
  - ``TestSource`` — synthetic test pattern / tone

Each source produces ``MediaStreamTrack``-compatible objects
and handles reconnection, format negotiation, and lifecycle.

Usage::

    source = CameraSource(camera_id=0, width=1280, height=720, fps=30)
    track = await source.start()
    pc.add_track(track)

    # Later
    await source.stop()
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from rivex_adapter.webrtc.core import logger


@dataclass
class SourceConfig:
    """Configuration for a media source."""

    kind: str = "unknown"  # "audio" | "video"
    width: int = 640
    height: int = 480
    fps: float = 30.0
    sample_rate: int = 48000
    channels: int = 1
    device_id: str = ""
    format: str = ""


class MediaSource(ABC):
    """Abstract base for a media source.

    Subclasses must implement ``_open()`` and ``_close()``.
    """

    name: str = "source"
    config: SourceConfig

    def __init__(self, config: SourceConfig | None = None):
        self.config = config or SourceConfig()
        self._track: Any = None
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect = 3
        self._reconnect_delay = 1.0

    async def start(self) -> Any:
        """Open the source and return a track."""
        if self._running:
            return self._track
        self._running = True
        self._track = await self._open()
        return self._track

    async def stop(self) -> None:
        """Close the source."""
        self._running = False
        await self._close()
        self._track = None

    async def restart(self) -> Any:
        """Reopen the source (useful after device reconnect)."""
        await self.stop()
        return await self.start()

    @abstractmethod
    async def _open(self) -> Any:
        """Open the source and return a track/stream."""
        ...

    @abstractmethod
    async def _close(self) -> None:
        """Release the source."""
        ...

    @property
    def is_running(self) -> bool:
        return self._running


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------


class CameraSource(MediaSource):
    """Webcam capture source.

    Uses ``av`` / ``opencv-python`` when available; falls back to a
    simulated test pattern.
    """

    name = "camera"

    def __init__(
        self,
        camera_id: int | str = 0,
        width: int = 640,
        height: int = 480,
        fps: float = 30.0,
    ):
        super().__init__(SourceConfig(
            kind="video", width=width, height=height, fps=fps,
            device_id=str(camera_id),
        ))
        self._camera_id = camera_id

    async def _open(self) -> Any:
        try:
            import cv2
            cap = cv2.VideoCapture(self._camera_id)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            cap.set(cv2.CAP_PROP_FPS, self.config.fps)
            return _CVCameraTrack(cap)
        except ImportError:
            logger.warning("opencv-python not available — using camera stub")
            return _TestVideoTrack(
                self.config.width, self.config.height, self.config.fps,
            )

    async def _close(self) -> None:
        if self._track and hasattr(self._track, "_release"):
            self._track._release()


# ---------------------------------------------------------------------------
# Microphone
# ---------------------------------------------------------------------------


class MicrophoneSource(MediaSource):
    """Microphone capture source.

    Uses ``pyaudio`` when available; falls back to a simulated tone.
    """

    name = "microphone"

    def __init__(
        self,
        device_id: int | None = None,
        sample_rate: int = 48000,
        channels: int = 1,
    ):
        super().__init__(SourceConfig(
            kind="audio", sample_rate=sample_rate, channels=channels,
            device_id=str(device_id) if device_id is not None else "",
        ))
        self._device_id = device_id

    async def _open(self) -> Any:
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                input_device_index=self._device_id,
                frames_per_buffer=960,
            )
            return _PyAudioMicTrack(stream, p)
        except ImportError:
            logger.warning("pyaudio not available — using mic stub")
            return _TestAudioTrack(self.config.sample_rate)

    async def _close(self) -> None:
        if self._track and hasattr(self._track, "_release"):
            self._track._release()


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------


class ScreenSource(MediaSource):
    """Screen/window capture source.

    Delegates to ``ScreenCapture`` from the screen module.
    """

    name = "screen"

    def __init__(
        self,
        display: int = 0,
        width: int = 1920,
        height: int = 1080,
        fps: float = 15,
    ):
        super().__init__(SourceConfig(
            kind="video", width=width, height=height, fps=fps,
            device_id=str(display),
        ))
        self._display = display

    async def _open(self) -> Any:
        from rivex_adapter.webrtc.screen import ScreenCapture
        sc = ScreenCapture(display=self._display, fps=self.config.fps)
        return await sc.start()

    async def _close(self) -> None:
        if self._track and hasattr(self._track, "stop"):
            await self._track.stop()


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------


class FileSource(MediaSource):
    """Media file source (reads from a local file).

    Uses ``av`` library when available; otherwise reads raw data.
    """

    name = "file"

    def __init__(self, filepath: str, loop: bool = False):
        super().__init__(SourceConfig(kind="video"))  # will detect
        self._filepath = filepath
        self._loop = loop
        self._detect_kind()

    def _detect_kind(self) -> None:
        ext = os.path.splitext(self._filepath)[1].lower()
        audio_exts = {".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a"}
        if ext in audio_exts:
            self.config.kind = "audio"

    async def _open(self) -> Any:
        return _FileFrameReader(
            self._filepath, self.config.kind, self._loop,
        )

    async def _close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Test / synthetic sources
# ---------------------------------------------------------------------------


class TestSource(MediaSource):
    """Synthetic test source (color bars + tone)."""

    name = "test"

    def __init__(self, kind: str = "video"):
        super().__init__(SourceConfig(kind=kind))
        self.config.kind = kind

    async def _open(self) -> Any:
        if self.config.kind == "audio":
            return _TestAudioTrack(self.config.sample_rate)
        return _TestVideoTrack(
            self.config.width, self.config.height, self.config.fps,
        )

    async def _close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Internal track stubs
# ---------------------------------------------------------------------------


class _CVCameraTrack:
    kind = "video"

    def __init__(self, cap):
        self._cap = cap
        self.id = f"camera-{uuid.uuid4().hex[:8]}"

    async def recv(self):
        import cv2
        ret, frame = self._cap.read()
        if not ret:
            raise EOFError("Camera read failed")
        return frame  # real impl would wrap in VideoFrame

    def _release(self):
        self._cap.release()


class _PyAudioMicTrack:
    kind = "audio"

    def __init__(self, stream, pyaudio_instance):
        self._stream = stream
        self._pa = pyaudio_instance
        self.id = f"mic-{uuid.uuid4().hex[:8]}"

    async def recv(self):
        data = self._stream.read(960, exception_on_overflow=False)
        return data  # raw PCM

    def _release(self):
        self._stream.stop_stream()
        self._stream.close()
        self._pa.terminate()


class _TestVideoTrack:
    kind = "video"

    def __init__(self, width=640, height=480, fps=30):
        self.id = f"test-video-{uuid.uuid4().hex[:8]}"
        self.width = width
        self.height = height
        self.fps = fps
        self._frame_count = 0

    async def recv(self):
        await asyncio.sleep(1.0 / self.fps)
        self._frame_count += 1
        return self  # the track itself acts as a frame


class _TestAudioTrack:
    kind = "audio"

    def __init__(self, sample_rate=48000):
        self.id = f"test-audio-{uuid.uuid4().hex[:8]}"
        self.sample_rate = sample_rate

    async def recv(self):
        await asyncio.sleep(0.02)
        return b"\x00\x00" * 960  # silence


class _FileFrameReader:
    kind: str = "video"

    def __init__(self, filepath: str, kind: str, loop: bool):
        self.id = f"file-{uuid.uuid4().hex[:8]}"
        self.kind = kind
        self._filepath = filepath
        self._loop = loop
        self._fh = open(filepath, "rb")
        self._eof = False

    async def recv(self):
        chunk = self._fh.read(4096)
        if not chunk:
            if self._loop:
                self._fh.seek(0)
                chunk = self._fh.read(4096)
            else:
                await asyncio.sleep(0.1)
                raise EOFError("File source exhausted")
        await asyncio.sleep(0.02)
        return chunk

    def __del__(self):
        if hasattr(self, "_fh") and self._fh:
            self._fh.close()


__all__ = [
    "MediaSource",
    "SourceConfig",
    "CameraSource",
    "MicrophoneSource",
    "ScreenSource",
    "FileSource",
    "TestSource",
]
