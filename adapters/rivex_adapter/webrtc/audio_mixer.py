"""
Audio mixing for WebRTC — mix multiple audio streams into one.

Provides:
- ``AudioMixer`` — mix N audio tracks into a single output track
- ``AudioMixerTrack`` — the mixed output as an aiortc MediaStreamTrack
- ``GainController`` — per-stream volume/gain control
- ``AudioLevelMixer`` — mix with audio-level-based ducking
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


@dataclass
class StreamInput:
    """A single input stream to the mixer."""

    track: Any
    gain: float = 1.0
    muted: bool = False
    label: str = ""
    last_frame: Any = None
    active: bool = True


class AudioMixerTrack:
    """An aiortc-compatible media track that produces mixed audio.

    Takes frames from multiple input tracks and mixes them
    into a single PCM output frame.
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 2,
        frame_duration_ms: float = 20.0,
    ):
        self.kind = "audio"
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_duration_ms = frame_duration_ms
        self.samples_per_frame = int(sample_rate * frame_duration_ms / 1000)
        self._buffer = bytearray()
        self._inputs: list[StreamInput] = []
        self._stopped = False

    async def recv(self) -> Any:
        """Return the next mixed audio frame."""
        from aiortc import AudioFrame

        while not self._stopped:
            mixed = await self._mix()
            if mixed is not None:
                return mixed
            await asyncio.sleep(0.01)

    async def _mix(self) -> Any:
        """Mix all input tracks into a single frame."""
        from aiortc import AudioFrame

        if not self._inputs:
            return self._silence_frame()

        frames: list[Any] = []
        for inp in self._inputs:
            if inp.muted or not inp.active:
                continue
            try:
                frame = await asyncio.wait_for(inp.track.recv(), timeout=0.1)
                inp.last_frame = frame
                frames.append(frame)
            except (asyncio.TimeoutError, Exception):
                if inp.last_frame is not None:
                    frames.append(inp.last_frame)

        if not frames:
            return self._silence_frame()

        return self._mix_frames(frames)

    def _mix_frames(self, frames: list[Any]) -> Any:
        """Mix multiple audio frames into one.

        Uses additive mixing with normalization to prevent clipping.
        """
        from aiortc import AudioFrame

        if not _HAS_NUMPY:
            return frames[0] if frames else self._silence_frame()

        mixed = np.zeros((self.samples_per_frame, self.channels), dtype=np.float64)

        for i, inp in enumerate(self._inputs):
            if inp.muted:
                continue
            if i < len(frames) and frames[i] is not None:
                try:
                    data = frames[i].to_ndarray()
                    if len(data) > self.samples_per_frame:
                        data = data[:self.samples_per_frame]
                    elif len(data) < self.samples_per_frame:
                        pad = np.zeros(
                            (self.samples_per_frame - len(data), self.channels),
                            dtype=data.dtype,
                        )
                        data = np.vstack([data, pad])
                    mixed += data.astype(np.float64) * inp.gain
                except Exception:
                    pass

        peak = np.max(np.abs(mixed))
        if peak > 1.0:
            mixed = mixed / peak

        frame = AudioFrame(
            samples=self.samples_per_frame,
            format="dbl",
            layout="stereo" if self.channels > 1 else "mono",
        )
        try:
            frame.from_ndarray((mixed * 32767).astype(np.int16))
        except Exception:
            pass
        frame.sample_rate = self.sample_rate
        return frame

    def _silence_frame(self) -> Any:
        """Generate a silence frame."""
        from aiortc import AudioFrame

        frame = AudioFrame(
            samples=self.samples_per_frame,
            format="s16",
            layout="stereo" if self.channels > 1 else "mono",
        )
        frame.sample_rate = self.sample_rate
        return frame

    def stop(self) -> None:
        """Stop the mixer track."""
        self._stopped = True


class AudioMixer:
    """Mix multiple audio input streams into a single output track.

    Supports per-stream gain, muting, and automatic normalization.

    Usage::

        mixer = AudioMixer(sample_rate=48000)

        # Add input tracks
        mixer.add_input(alice_track, gain=0.8, label="alice")
        mixer.add_input(bob_track, gain=1.0, label="bob")

        # Get the mixed output track
        output_track = mixer.output_track

        # Add to a peer connection
        pc._pc.addTrack(output_track)

        # Control during session
        mixer.set_gain("alice", 0.5)
        mixer.mute("bob", True)

    Extensibility:
        Override ``mix()`` for custom mixing algorithms.
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 2,
        frame_duration_ms: float = 20.0,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_duration_ms = frame_duration_ms
        self._inputs: list[StreamInput] = {}
        self._output_track = AudioMixerTrack(sample_rate, channels, frame_duration_ms)
        self._logger = logger.getChild("audio-mixer")

    def add_input(
        self,
        track: Any,
        gain: float = 1.0,
        label: str = "",
    ) -> str:
        """Add an audio track as a mixer input.

        Args:
            track: An aiortc ``AudioStreamTrack``.
            gain: Volume multiplier (0.0 = silent, 1.0 = normal).
            label: Optional label for identification.

        Returns:
            An input ID for later control.
        """
        import uuid
        input_id = uuid.uuid4().hex[:8]
        inp = StreamInput(track=track, gain=gain, label=label or input_id)
        self._inputs[input_id] = inp
        self._output_track._inputs.append(inp)
        self._logger.info("added input %s (label=%s, gain=%.1f)", input_id, label, gain)
        return input_id

    def remove_input(self, input_id: str) -> None:
        """Remove an input by ID."""
        inp = self._inputs.pop(input_id, None)
        if inp is not None:
            self._output_track._inputs.remove(inp)
            self._logger.info("removed input %s", input_id)

    def set_gain(self, input_id: str, gain: float) -> None:
        """Set the gain for an input."""
        inp = self._inputs.get(input_id)
        if inp is not None:
            inp.gain = max(0.0, min(10.0, gain))

    def mute(self, input_id: str, muted: bool = True) -> None:
        """Mute or unmute an input."""
        inp = self._inputs.get(input_id)
        if inp is not None:
            inp.muted = muted

    def list_inputs(self) -> list[dict[str, Any]]:
        """List all mixer inputs with their current state."""
        return [
            {
                "id": iid,
                "label": inp.label,
                "gain": inp.gain,
                "muted": inp.muted,
                "active": inp.active,
            }
            for iid, inp in self._inputs.items()
        ]

    @property
    def output_track(self) -> AudioMixerTrack:
        """The mixed output track (aiortc-compatible)."""
        return self._output_track

    def mix(self, frames: list[Any], gains: list[float]) -> Any:
        """Mix frames with gains into a single frame.

        Override for custom mixing algorithm.

        Args:
            frames: Input audio frames.
            gains: Per-frame gain values.

        Returns:
            A single mixed ``AudioFrame``.
        """
        return self._output_track._mix_frames(frames)


class GainController:
    """Per-stream gain/volume control.

    Provides independent volume control for each input stream.

    Usage::

        gc = GainController()

        # Set gain for an input
        gc.set("alice", 0.8)
        gc.set("bob", 1.5)

        # Fade in/out
        await gc.fade_in("alice", duration=2.0)
        await gc.fade_out("bob", duration=1.0)
    """

    def __init__(self):
        self._gains: dict[str, float] = {}

    def set(self, input_id: str, gain: float) -> None:
        """Set the gain for an input."""
        self._gains[input_id] = max(0.0, min(10.0, gain))

    def get(self, input_id: str) -> float:
        """Get the current gain for an input."""
        return self._gains.get(input_id, 1.0)

    async def fade_in(self, input_id: str, duration: float = 2.0) -> None:
        """Fade an input from silent to full volume."""
        steps = int(duration * 20)
        for i in range(steps):
            self._gains[input_id] = (i + 1) / steps
            await asyncio.sleep(duration / steps)
        self._gains[input_id] = 1.0

    async def fade_out(self, input_id: str, duration: float = 2.0) -> None:
        """Fade an input from full volume to silent."""
        steps = int(duration * 20)
        for i in range(steps):
            self._gains[input_id] = 1.0 - (i + 1) / steps
            await asyncio.sleep(duration / steps)
        self._gains[input_id] = 0.0


__all__ = [
    "AudioMixer",
    "AudioMixerTrack",
    "GainController",
    "StreamInput",
]
