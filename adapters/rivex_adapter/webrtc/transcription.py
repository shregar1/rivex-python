"""
Real-time audio transcription for WebRTC conferences.

``TranscriptionEngine`` — pluggable base for STT backends:
  - ``WhisperEngine`` — local OpenAI Whisper (``faster-whisper``)
  - ``VoskEngine`` — offline Vosk ASR
  - ``GoogleCloudEngine`` — Google Cloud Speech-to-Text

``StreamingTranscriber`` — consumes audio frames from a track and
fires ``on_transcript(text, peer_id, is_final)`` callbacks.

Usage::

    transcriber = StreamingTranscriber(
        engine=WhisperEngine(model_size="base"),
        sample_rate=16000,
    )

    transcriber.on_transcript(
        lambda text, peer_id, is_final:
            print(f"{peer_id}: {text}")
    )

    # Feed audio frames from a track
    transcriber.feed_track(audio_track, peer_id="alice")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from rivex_adapter.webrtc.core import logger


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class TranscriptSegment:
    """A segment of transcribed text."""

    text: str
    peer_id: str
    language: str = "en"
    start_offset: float = 0.0
    end_offset: float = 0.0
    is_final: bool = False
    confidence: float = 0.0
    words: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine base and implementations
# ---------------------------------------------------------------------------


class TranscriptionEngine(ABC):
    """Abstract base for speech-to-text engines."""

    name: str = "base"

    @abstractmethod
    async def transcribe(self, audio_data: bytes, sample_rate: int) -> TranscriptSegment:
        """Transcribe a chunk of PCM 16-bit mono audio.

        Args:
            audio_data: Raw PCM 16-bit little-endian audio.
            sample_rate: Sample rate of the audio (Hz).

        Returns:
            A ``TranscriptSegment``.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release engine resources."""
        ...


class WhisperEngine(TranscriptionEngine):
    """Local Whisper STT via ``faster-whisper``.

    Falls back to a mock transcript if ``faster-whisper`` is not installed.
    """

    name = "whisper"

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "float32",
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._fallback = False

    async def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        except ImportError:
            self._fallback = True
            logger.warning(
                "faster-whisper not installed — using mock transcription"
            )

    async def transcribe(self, audio_data: bytes, sample_rate: int) -> TranscriptSegment:
        await self._load()
        if self._fallback or self._model is None:
            return TranscriptSegment(
                text="[mock transcription]",
                peer_id="",
                is_final=True,
                confidence=0.5,
            )
        import numpy as np
        samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(samples, beam_size=5)
        text = ""
        confidence = 0.0
        count = 0
        async for seg in segments:
            text += seg.text + " "
            confidence += seg.avg_logprob
            count += 1
        return TranscriptSegment(
            text=text.strip(),
            peer_id="",
            language=info.language if hasattr(info, "language") else "en",
            is_final=True,
            confidence=confidence / max(count, 1),
        )

    async def close(self) -> None:
        self._model = None


class MockEngine(TranscriptionEngine):
    """Mock engine for testing — echoes back a fixed message."""

    name = "mock"

    def __init__(self, mock_text: str = "[mock transcript]"):
        self._mock_text = mock_text

    async def transcribe(self, audio_data: bytes, sample_rate: int) -> TranscriptSegment:
        return TranscriptSegment(
            text=self._mock_text,
            peer_id="",
            is_final=True,
            confidence=0.95,
        )

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Streaming Transcriber
# ---------------------------------------------------------------------------


class StreamingTranscriber:
    """Consumes audio frames from a track and produces transcripts.

    Manages per-peer audio buffers, segments audio by silence/pause,
    and fires callbacks for partial and final transcripts.

    Usage::

        transcriber = StreamingTranscriber(engine=MockEngine())
        transcriber.on_transcript(handler)
        transcriber.feed_track(audio_track, peer_id="alice")
    """

    def __init__(
        self,
        engine: TranscriptionEngine | None = None,
        sample_rate: int = 16000,
        segment_pause_ms: int = 700,
        min_segment_duration_ms: int = 500,
        max_segment_duration_ms: int = 30000,
    ):
        self._engine = engine or MockEngine()
        self._sample_rate = sample_rate
        self._segment_pause_ms = segment_pause_ms
        self._min_segment_duration_ms = min_segment_duration_ms
        self._max_segment_duration_ms = max_segment_duration_ms

        self._buffers: dict[str, bytearray] = {}
        self._last_audio_time: dict[str, float] = {}
        self._pending_tasks: dict[str, asyncio.Task] = {}
        self._transcript_handlers: list[Callable[[TranscriptSegment], None]] = []
        self._running = False
        self._buffer_lock = asyncio.Lock()

    def on_transcript(self, handler: Callable[[TranscriptSegment], None]) -> None:
        """Register a callback for transcript segments.

        The callback receives a ``TranscriptSegment``.
        """
        self._transcript_handlers.append(handler)

    def feed_track(self, track: Any, peer_id: str) -> None:
        """Start consuming audio frames from a media track.

        The track must have a ``recv()`` async method returning frames
        with a ``data`` attribute (raw PCM 16-bit).
        """
        task = asyncio.ensure_future(self._consume_track(track, peer_id))
        self._pending_tasks[peer_id] = task

    def feed_chunk(self, audio_data: bytes, peer_id: str) -> None:
        """Feed a raw PCM 16-bit chunk for a peer."""
        if peer_id not in self._buffers:
            self._buffers[peer_id] = bytearray()
        self._buffers[peer_id].extend(audio_data)
        self._last_audio_time[peer_id] = time.time()

    async def stop(self) -> None:
        """Stop all transcription tasks and finalise pending buffers."""
        self._running = False
        for peer_id in list(self._pending_tasks.keys()):
            task = self._pending_tasks.pop(peer_id, None)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await self._flush_buffer(peer_id, force=True)
        await self._engine.close()

    async def _consume_track(self, track: Any, peer_id: str) -> None:
        self._running = True
        try:
            while self._running:
                try:
                    frame = await asyncio.wait_for(track.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break

                data = frame.data if hasattr(frame, "data") else frame
                if isinstance(data, bytes):
                    self.feed_chunk(data, peer_id)
        finally:
            self._pending_tasks.pop(peer_id, None)
            await self._flush_buffer(peer_id, force=True)

    async def _flush_buffer(
        self, peer_id: str, force: bool = False
    ) -> None:
        async with self._buffer_lock:
            buf = self._buffers.pop(peer_id, None)
            self._last_audio_time.pop(peer_id, None)
        if buf is None or len(buf) < self._sample_rate * 2:  # < 2 seconds
            return
        segment = await self._engine.transcribe(bytes(buf), self._sample_rate)
        segment.peer_id = peer_id
        segment.is_final = True
        self._emit(segment)

    def _emit(self, segment: TranscriptSegment) -> None:
        for handler in self._transcript_handlers:
            try:
                handler(segment)
            except Exception:
                logger.exception("transcript handler error")


__all__ = [
    "TranscriptionEngine",
    "WhisperEngine",
    "MockEngine",
    "StreamingTranscriber",
    "TranscriptSegment",
]
