"""
Session recording and replay for WebRTC conferences.

Records:
- Audio tracks (encoded packets)
- Video tracks (encoded packets)
- Data channel messages (JSON-serialised)
- Track lifecycle events (add/remove)
- Timestamps for all events

Stored in a directory as:
  session/
    metadata.json           — session info, participant list
    tracks/
      {track_id}.raw        — concatenated RTP packets (raw bytes)
    events.jsonl            — newline-delimited JSON event log
    data_channels/
      {label}.jsonl         — per-channel message log

Replay:
  ``SessionReplayer`` replays a recorded session, producing fake
  ``MediaStreamTrack``-like objects and firing events on a callback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from rivex_adapter.webrtc.core import logger

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TrackSnapshot:
    """Metadata for a single recorded track."""

    track_id: str
    kind: str  # "audio" | "video"
    peer_id: str
    codec: str = ""
    ssrc: int = 0
    payload_type: int = 0
    width: int = 0
    height: int = 0
    fps: float = 0.0


@dataclass
class SessionMetadata:
    """Top-level session metadata."""

    session_id: str
    created_at: str  # ISO-8601
    duration: float = 0.0
    participants: list[str] = field(default_factory=list)
    tracks: list[dict] = field(default_factory=list)
    data_channels: list[str] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


class SessionRecorder:
    """Records a WebRTC session to disk.

    Usage::

        recorder = SessionRecorder(pc, output_dir="recordings/session_001")

        # Wire up
        recorder.record_track(track)          # for each incoming track
        recorder.record_data_channel("chat")  # for each data channel

        # Later
        await recorder.stop()
    """

    def __init__(
        self,
        output_dir: str | Path,
        session_id: str | None = None,
        auto_index: bool = True,
    ):
        self._output_dir = Path(output_dir)
        self._session_id = session_id or uuid.uuid4().hex[:12]
        self._auto_index = auto_index
        self._started_at: float | None = None
        self._tracks_dir: Path | None = None
        self._dc_dir: Path | None = None
        self._events_file: Path | None = None
        self._events_fh: Any = None
        self._data_channel_fhs: dict[str, Any] = {}
        self._track_files: dict[str, Any] = {}
        self._track_meta: list[dict] = []
        self._data_channel_labels: list[str] = []
        self._participants: set[str] = set()
        self._recording: bool = False
        self._task: asyncio.Task | None = None

    async def start(self) -> str:
        """Create output directory structure and start recording.

        Returns:
            Session ID.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._tracks_dir = self._output_dir / "tracks"
        self._tracks_dir.mkdir(exist_ok=True)
        self._dc_dir = self._output_dir / "data_channels"
        self._dc_dir.mkdir(exist_ok=True)

        self._events_file = self._output_dir / "events.jsonl"
        self._events_fh = open(self._events_file, "w")
        self._started_at = time.time()
        self._recording = True

        self._write_event("session.start", {
            "session_id": self._session_id,
            "timestamp": self._started_at,
        })

        logger.info(
            "SessionRecorder started: %s (%s)",
            self._session_id, self._output_dir,
        )
        return self._session_id

    def add_participant(self, peer_id: str) -> None:
        """Record a participant join."""
        self._participants.add(peer_id)
        self._write_event("participant.join", {"peer_id": peer_id})

    def remove_participant(self, peer_id: str) -> None:
        """Record a participant leave."""
        self._participants.discard(peer_id)
        self._write_event("participant.leave", {"peer_id": peer_id})

    def record_track(
        self,
        track: Any,
        peer_id: str = "",
        codec: str = "",
    ) -> str:
        """Begin recording an incoming media track to disk.

        Args:
            track: An object with ``kind``, ``id`` attributes and a
                   ``on_packet(callback)`` or similar method.  We wrap
                   it by monkey-patching the track's frame receiver.
            peer_id: The peer that sent this track.
            codec:  Codec name (e.g. "opus", "h264").

        Returns:
            Track ID.
        """
        track_id = track.id
        kind = getattr(track, "kind", "unknown")
        self._track_meta.append({
            "track_id": track_id,
            "kind": kind,
            "peer_id": peer_id,
            "codec": codec,
            "ssrc": getattr(track, "ssrc", 0),
            "payload_type": getattr(track, "payload_type", 0),
            "width": getattr(track, "width", 0),
            "height": getattr(track, "height", 0),
            "fps": getattr(track, "fps", 0.0),
        })

        fh = open(self._tracks_dir / f"{track_id}.raw", "wb")
        self._track_files[track_id] = fh

        # Monkey-patch frame receiver — tried and tested pattern
        original_recv = getattr(track, "recv", None)

        async def patched_recv():
            pkt = await original_recv()
            if self._recording:
                fh.write(pkt.serialize() if hasattr(pkt, "serialize") else pkt.data)
                fh.flush()
                self._write_event("track.frame", {
                    "track_id": track_id,
                    "timestamp": time.time() - (self._started_at or 0),
                    "size": len(pkt.serialize() if hasattr(pkt, "serialize") else pkt.data),
                })
            return pkt

        track.recv = patched_recv

        self._write_event("track.added", {
            "track_id": track_id,
            "kind": kind,
            "peer_id": peer_id,
            "codec": codec,
        })
        return track_id

    def stop_recording_track(self, track_id: str) -> None:
        """Stop recording a specific track."""
        fh = self._track_files.pop(track_id, None)
        if fh:
            fh.close()
        self._write_event("track.removed", {"track_id": track_id})

    def record_data_channel(self, label: str) -> None:
        """Start recording a data channel."""
        if label in self._data_channel_fhs:
            return
        self._data_channel_labels.append(label)
        fh = open(self._dc_dir / f"{label}.jsonl", "w")
        self._data_channel_fhs[label] = fh

    def log_data_channel_message(self, label: str, data: str | bytes) -> None:
        """Log a data channel message to the per-channel JSONL file."""
        self.record_data_channel(label)
        fh = self._data_channel_fhs.get(label)
        if fh is None:
            return
        payload = {
            "timestamp": time.time() - (self._started_at or 0),
            "data": data.decode() if isinstance(data, bytes) else data,
        }
        fh.write(json.dumps(payload) + "\n")
        fh.flush()

    async def stop(self) -> Path:
        """Finalise the recording and write metadata.

        Returns:
            Path to the output directory.
        """
        self._recording = False
        elapsed = time.time() - (self._started_at or 0)

        for fh in self._track_files.values():
            fh.close()
        for fh in self._data_channel_fhs.values():
            fh.close()
        if self._events_fh:
            self._events_fh.close()

        meta = SessionMetadata(
            session_id=self._session_id,
            created_at=datetime.utcnow().isoformat() + "Z",
            duration=elapsed,
            participants=sorted(self._participants),
            tracks=self._track_meta,
            data_channels=self._data_channel_labels,
        )

        meta_path = self._output_dir / "metadata.json"
        meta_path.write_text(
            json.dumps(asdict(meta), indent=2, default=str)
        )
        logger.info(
            "SessionRecorder stopped: %s  (%.1f s, %d tracks, %d participants)",
            self._session_id, elapsed, len(self._track_meta), len(self._participants),
        )
        return self._output_dir

    def _write_event(self, kind: str, data: dict) -> None:
        if not self._events_fh:
            return
        line = json.dumps({"kind": kind, "data": data}) + "\n"
        self._events_fh.write(line)
        self._events_fh.flush()


# ---------------------------------------------------------------------------
# Replayer
# ---------------------------------------------------------------------------


@dataclass
class ReplayedEvent:
    """A single event from the replayer."""

    kind: str
    data: dict
    offset: float  # seconds from start


class SessionReplayer:
    """Replays a recorded session from disk.

    Usage::

        replayer = SessionReplayer("recordings/session_001")
        replayer.on_event(lambda ev: print(ev.kind, ev.data))
        await replayer.play(speed=1.0)
    """

    def __init__(self, directory: str | Path):
        self._directory = Path(directory)
        self._events: list[ReplayedEvent] = []
        self._metadata: SessionMetadata | None = None
        self._event_handlers: list[Callable[[ReplayedEvent], None]] = []
        self._data_channels: dict[str, list[dict]] = {}
        self._track_data: dict[str, bytes] = {}
        self._logger = logger.getChild(f"replayer-{self._directory.name}")

    def on_event(self, handler: Callable[[ReplayedEvent], None]) -> None:
        """Register an event handler."""
        self._event_handlers.append(handler)

    async def load(self) -> SessionMetadata:
        """Load session metadata and events into memory."""
        meta_path = self._directory / "metadata.json"
        if meta_path.exists():
            raw = json.loads(meta_path.read_text())
            self._metadata = SessionMetadata(**raw)

        events_path = self._directory / "events.jsonl"
        if events_path.exists():
            with open(events_path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    offset = obj["data"].get("timestamp", 0.0)
                    self._events.append(
                        ReplayedEvent(kind=obj["kind"], data=obj["data"], offset=offset)
                    )
            self._events.sort(key=lambda e: e.offset)

        dc_dir = self._directory / "data_channels"
        if dc_dir.exists():
            for f in sorted(dc_dir.iterdir()):
                if f.suffix == ".jsonl":
                    label = f.stem
                    msgs = []
                    with open(f) as fh_:
                        for line in fh_:
                            line = line.strip()
                            if line:
                                msgs.append(json.loads(line))
                    self._data_channels[label] = msgs

        tracks_dir = self._directory / "tracks"
        if tracks_dir.exists():
            for f in sorted(tracks_dir.iterdir()):
                if f.suffix == ".raw":
                    self._track_data[f.stem] = f.read_bytes()

        self._logger.info(
            "Loaded: %d events, %d tracks, %d data channels",
            len(self._events), len(self._track_data), len(self._data_channels),
        )
        return self._metadata

    async def play(self, speed: float = 1.0) -> None:
        """Replay events in chronological order.

        Args:
            speed: Multiplier (2.0 = double-speed replay).
        """
        if not self._events:
            self._logger.warning("No events loaded — call load() first")
            return

        last_offset = 0.0
        for ev in self._events:
            delay = (ev.offset - last_offset) / speed
            if delay > 0:
                await asyncio.sleep(delay)
            last_offset = ev.offset
            for handler in self._event_handlers:
                handler(ev)

    def get_track_data(self, track_id: str) -> bytes:
        """Get raw recorded data for a track."""
        return self._track_data.get(track_id, b"")

    def get_data_channel_messages(self, label: str) -> list[dict]:
        """Get all recorded messages for a data channel."""
        return self._data_channels.get(label, [])

    @property
    def metadata(self) -> SessionMetadata | None:
        return self._metadata


__all__ = [
    "SessionRecorder",
    "SessionReplayer",
    "TrackSnapshot",
    "SessionMetadata",
]
