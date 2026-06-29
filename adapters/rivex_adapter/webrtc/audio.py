"""
Audio processing for WebRTC: VAD, noise suppression, level detection.

Provides:
- ``AudioLevelIndicator`` — detect audio activity on a track
- ``VoiceActivityDetector`` — voice activity detection (VAD)
- ``NoiseSuppressor`` — background noise suppression
- ``AudioPipeline`` — chain multiple audio processors
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

try:
    import webrtcvad
    _HAS_WEBRTCVAD = True
except ImportError:
    _HAS_WEBRTCVAD = False

try:
    import noisereduce as nr
    _HAS_NOISEREDUCE = True
except ImportError:
    _HAS_NOISEREDUCE = False


# ---------------------------------------------------------------------------
# Audio Level Indicator
# ---------------------------------------------------------------------------


class AudioLevelIndicator:
    """Detect audio energy/activity level on an audio track.

    Computes RMS (root mean square) energy on each frame and
    reports it via callbacks. Useful for voice activity visualization
    (e.g. "talking" indicator in a conference UI).

    Usage::

        level = AudioLevelIndicator()
        level.on_level(lambda db: print(f"Audio level: {db:.1f} dB"))
        level.on_activity(lambda active: print("Speaking!" if active else "Silent"))

        # Wrap an aiortc AudioStreamTrack
        wrapped = level.wrap(track)

    Extensibility:
        Override ``compute_rms()`` or ``classify_activity()``
        to customize level/activity detection.
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        threshold_db: float = -40.0,
        hold_frames: int = 5,
    ):
        self.sample_rate = sample_rate
        self.threshold_db = threshold_db
        self.hold_frames = hold_frames
        self._level_callbacks: list[Callable[[float], None]] = []
        self._activity_callbacks: list[Callable[[bool], None]] = []
        self._active = False
        self._silent_frames = 0
        self._logger = logger.getChild("audio-level")

    def on_level(self, callback: Callable[[float], None]) -> None:
        """Called with RMS level in dB for each frame."""
        self._level_callbacks.append(callback)

    def on_activity(self, callback: Callable[[bool], None]) -> None:
        """Called with ``True`` when speech starts, ``False`` when silence."""
        self._activity_callbacks.append(callback)

    def compute_rms(self, frame: Any) -> float:
        """Compute RMS power of an audio frame in dB.

        Override for custom level computation.
        """
        try:
            data = frame.to_ndarray()
            if _HAS_NUMPY:
                rms = np.sqrt(np.mean(data.astype(np.float64) ** 2))
                if rms > 0:
                    return 20.0 * np.log10(rms)
                return -100.0
            samples = struct.unpack(f"<{len(data) // 2}h", data)
            if not samples:
                return -100.0
            sum_sq = sum(s * s for s in samples)
            rms = (sum_sq / len(samples)) ** 0.5
            if rms > 0:
                return 20.0 * (rms ** 0.5)
            return -100.0
        except Exception:
            return -100.0

    def classify_activity(self, level_db: float) -> bool:
        """Determine if the audio level indicates active speech.

        Override for custom activity classification.
        """
        return level_db > self.threshold_db

    def wrap(self, source_track: Any) -> Any:
        """Wrap an aiortc ``AudioStreamTrack`` with level detection.

        Returns a new track proxy that computes levels on each frame.
        """
        from aiortc import MediaStreamTrack

        class _LevelTrack(MediaStreamTrack):
            kind = source_track.kind

            def __init__(self, indicator: AudioLevelIndicator, source: Any):
                super().__init__()
                self._indicator = indicator
                self._source = source

            async def recv(self) -> Any:
                frame = await self._source.recv()
                level_db = self._indicator.compute_rms(frame)

                for cb in self._indicator._level_callbacks:
                    cb(level_db)

                was_active = self._indicator._active
                is_active = self._indicator.classify_activity(level_db)

                if is_active:
                    self._indicator._silent_frames = 0
                    if not was_active:
                        self._indicator._active = True
                        for cb in self._indicator._activity_callbacks:
                            cb(True)
                else:
                    self._indicator._silent_frames += 1
                    if (
                        was_active
                        and self._indicator._silent_frames >= self._indicator.hold_frames
                    ):
                        self._indicator._active = False
                        for cb in self._indicator._activity_callbacks:
                            cb(False)

                return frame

        return _LevelTrack(self, source_track)


# ---------------------------------------------------------------------------
# Voice Activity Detection
# ---------------------------------------------------------------------------


class VoiceActivityDetector:
    """Voice Activity Detection using WebRTC VAD.

    Requires ``webrtcvad``: ``pip install webrtcvad``

    Usage::

        vad = VoiceActivityDetector(mode=2)
        vad.on_voice(lambda: print("Voice detected!"))
        vad.on_silence(lambda: print("Silence"))

        wrapped = vad.wrap(track)

    Extensibility:
        Override ``process_frame()`` to customize VAD logic.
    """

    def __init__(
        self,
        mode: int = 2,
        sample_rate: int = 48000,
        frame_duration_ms: int = 30,
    ):
        if not _HAS_WEBRTCVAD:
            raise RuntimeError(
                "webrtcvad is required for VoiceActivityDetector. "
                "Install: pip install webrtcvad"
            )
        self.mode = mode
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self._vad = webrtcvad.Vad(mode)
        self._voice_callbacks: list[Callable[[], None]] = []
        self._silence_callbacks: list[Callable[[], None]] = []
        self._is_voice = False

    def on_voice(self, callback: Callable[[], None]) -> None:
        """Called when voice is detected."""
        self._voice_callbacks.append(callback)

    def on_silence(self, callback: Callable[[], None]) -> None:
        """Called when silence is detected."""
        self._silence_callbacks.append(callback)

    def process_frame(self, frame: Any) -> bool:
        """Process an audio frame and return whether voice is active.

        Override for custom VAD logic.
        """
        data = frame.to_ndarray()
        if _HAS_NUMPY:
            pcm = (data * 32767).astype(np.int16).tobytes()
        else:
            pcm = data.tobytes()

        return self._vad.is_speech(pcm, self.sample_rate)

    def wrap(self, source_track: Any) -> Any:
        """Wrap an aiortc ``AudioStreamTrack`` with VAD."""
        from aiortc import MediaStreamTrack

        class _VADTrack(MediaStreamTrack):
            kind = source_track.kind

            def __init__(self, detector: VoiceActivityDetector, source: Any):
                super().__init__()
                self._detector = detector
                self._source = source

            async def recv(self) -> Any:
                frame = await self._source.recv()
                is_voice = self._detector.process_frame(frame)

                if is_voice and not self._detector._is_voice:
                    self._detector._is_voice = True
                    for cb in self._detector._voice_callbacks:
                        cb()
                elif not is_voice and self._detector._is_voice:
                    self._detector._is_voice = False
                    for cb in self._detector._silence_callbacks:
                        cb()

                return frame

        return _VADTrack(self, source_track)


# ---------------------------------------------------------------------------
# Noise Suppressor
# ---------------------------------------------------------------------------


class NoiseSuppressor:
    """Background noise suppression for audio tracks.

    Requires ``noisereduce``: ``pip install noisereduce``
    and ``numpy``: ``pip install numpy``

    Usage::

        suppressor = NoiseSuppressor()
        wrapped = suppressor.wrap(track)

    Extensibility:
        Override ``reduce_noise()`` for custom suppression algorithm.
    """

    def __init__(
        self,
        stationary: bool = True,
        prop_decrease: float = 1.0,
        time_constant_s: float = 2.0,
    ):
        if not _HAS_NOISEREDUCE:
            raise RuntimeError(
                "noisereduce is required for NoiseSuppressor. "
                "Install: pip install noisereduce"
            )
        self.stationary = stationary
        self.prop_decrease = prop_decrease
        self.time_constant_s = time_constant_s
        self._sample_rate: int | None = None

    def reduce_noise(self, audio_data: Any, sample_rate: int) -> Any:
        """Apply noise reduction to audio data.

        Override for custom noise suppression.
        """
        return nr.reduce_noise(
            y=audio_data,
            sr=sample_rate,
            stationary=self.stationary,
            prop_decrease=self.prop_decrease,
            time_constant_s=self.time_constant_s,
        )

    def wrap(self, source_track: Any) -> Any:
        """Wrap an aiortc ``AudioStreamTrack`` with noise suppression."""
        from aiortc import MediaStreamTrack

        class _NoiseReducedTrack(MediaStreamTrack):
            kind = source_track.kind

            def __init__(self, suppressor: NoiseSuppressor, source: Any):
                super().__init__()
                self._suppressor = suppressor
                self._source = source

            async def recv(self) -> Any:
                frame = await self._source.recv()
                if not _HAS_NUMPY:
                    return frame
                audio = frame.to_ndarray()
                sample_rate = getattr(frame, "sample_rate", 48000)
                cleaned = self._suppressor.reduce_noise(audio, sample_rate)
                return frame.from_ndarray(cleaned)

        return _NoiseReducedTrack(self, source_track)


# ---------------------------------------------------------------------------
# Audio Pipeline
# ---------------------------------------------------------------------------


class AudioPipeline:
    """Chain multiple audio processors.

    Each processor wraps the track sequentially, forming a pipeline.

    Usage::

        pipeline = AudioPipeline()
        pipeline.add(noise_suppressor)
        pipeline.add(vad_detector)
        pipeline.add(level_indicator)

        wrapped = pipeline.wrap(original_track)
    """

    def __init__(self):
        self._processors: list[Any] = []

    def add(self, processor: Any) -> None:
        """Add an audio processor to the pipeline.

        The processor must have a ``wrap(track)`` method.
        """
        self._processors.append(processor)

    def remove(self, processor: Any) -> None:
        """Remove a processor from the pipeline."""
        self._processors.remove(processor)

    def clear(self) -> None:
        """Remove all processors."""
        self._processors.clear()

    def wrap(self, source_track: Any) -> Any:
        """Wrap an audio track with all processors.

        Processors are applied in registration order.
        """
        track = source_track
        for processor in self._processors:
            track = processor.wrap(track)
        return track

    @property
    def processors(self) -> list[Any]:
        return list(self._processors)

    def __len__(self) -> int:
        return len(self._processors)


__all__ = [
    "AudioLevelIndicator",
    "VoiceActivityDetector",
    "NoiseSuppressor",
    "AudioPipeline",
]
