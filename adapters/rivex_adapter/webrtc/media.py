"""
Media handling for WebRTC: recording, file sinks, and selective forwarding.

Provides:
- ``MediaRecorder`` — record audio/video to a file
- ``MediaFileSink`` — consume and discard media (blackhole)
- ``SelectiveForwardingUnit`` — abstract SFU interface
- ``InMemorySFU`` — in-memory SFU that relays tracks between peers
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger

# ---------------------------------------------------------------------------
# Media Recorder
# ---------------------------------------------------------------------------


class MediaRecorder:
    """Record WebRTC media tracks to a file.

    Uses ``aiortc``'s ``MediaRecorder`` under the hood. Supports
    common container formats based on file extension.

    Usage::

        recorder = MediaRecorder("output.mp4")
        recorder.add_track(audio_track)
        recorder.add_track(video_track)
        await recorder.start()
        # ... later ...
        await recorder.stop()

    Extensibility:
        Subclass and override ``_create_recorder()`` to customize
        the underlying aiortc ``MediaRecorder``.
    """

    def __init__(
        self,
        filepath: str,
        format: str | None = None,
        video_codec: str | None = None,
        audio_codec: str | None = None,
    ):
        self.filepath = filepath
        self.format = format or self._infer_format(filepath)
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self._recorder: Any = None
        self._tracks: list[Any] = []
        self._started = False
        self._logger = logger.getChild(f"recorder-{os.path.basename(filepath)}")

    def add_track(self, track: Any) -> None:
        """Add a media track to the recording.

        Can be called before or after ``start()``. Tracks added
        after ``start()`` are added to the underlying recorder immediately.
        """
        self._tracks.append(track)
        if self._recorder is not None:
            self._recorder.addTrack(track)
            self._logger.debug("added track %s to recorder", track.kind if hasattr(track, "kind") else "?")

    async def start(self) -> None:
        """Start recording.

        Creates the underlying recorder and begins consuming tracks.
        """
        from aiortc.contrib.media import MediaRecorder as AioRtcRecorder

        self._recorder = self._create_recorder(AioRtcRecorder)
        for track in self._tracks:
            self._recorder.addTrack(track)
        await self._recorder.start()
        self._started = True
        self._logger.info("recording started: %s", self.filepath)

    async def stop(self) -> None:
        """Stop recording and finalize the file."""
        if self._recorder is not None and self._started:
            await self._recorder.stop()
            self._started = False
            self._logger.info("recording stopped: %s", self.filepath)

    def _infer_format(self, filepath: str) -> str:
        ext = os.path.splitext(filepath)[1].lower()
        format_map = {
            ".mp4": "mp4",
            ".webm": "webm",
            ".ogg": "ogg",
            ".wav": "wav",
            ".mkv": "mkv",
            ".flv": "flv",
            ".avi": "avi",
        }
        return format_map.get(ext, "mp4")

    def _create_recorder(self, recorder_class: type) -> Any:
        """Create and return the underlying ``MediaRecorder``.

        Override to configure custom options, filters, or codec params.
        """
        kwargs: dict[str, Any] = {}
        if self.video_codec:
            kwargs["videoCodec"] = self.video_codec
        if self.audio_codec:
            kwargs["audioCodec"] = self.audio_codec
        return recorder_class(self.filepath, format=self.format, **kwargs)


# ---------------------------------------------------------------------------
# Media File Sink (blackhole)
# ---------------------------------------------------------------------------


class MediaFileSink:
    """Consume and discard WebRTC media tracks.

    Useful for "blackhole" receivers that accept media but don't
    process it (e.g. for headless recording or stats collection).

    Usage::

        sink = MediaFileSink()
        sink.add_track(track)
        await sink.start()
        # tracks are consumed and discarded
        await sink.stop()
    """

    def __init__(self):
        self._player: Any = None
        self._tracks: list[Any] = []
        self._started = False

    def add_track(self, track: Any) -> None:
        """Add a track to be consumed and discarded."""
        self._tracks.append(track)

    async def start(self) -> None:
        """Start consuming tracks."""
        from aiortc.contrib.media import MediaBlackhole

        self._player = MediaBlackhole()
        for track in self._tracks:
            self._player.addTrack(track)
        await self._player.start()
        self._started = True
        logger.debug("media sink started (%d tracks)", len(self._tracks))

    async def stop(self) -> None:
        """Stop consuming tracks."""
        if self._player is not None and self._started:
            await self._player.stop()
            self._started = False


# ---------------------------------------------------------------------------
# Selective Forwarding Unit (abstract)
# ---------------------------------------------------------------------------


class SelectiveForwardingUnit:
    """Abstract base for a Selective Forwarding Unit (SFU).

    An SFU receives media tracks from publishers and selectively
    forwards them to subscribers, allowing N-way media without
    the O(N^2) uplink cost of full mesh.

    Subclasses must implement ``publish()`` and ``subscribe()``.
    """

    async def publish(
        self,
        publisher_id: str,
        pc: WebRTCPeerConnection,
        track: Any,
    ) -> str:
        """Publish a media track from a peer.

        Args:
            publisher_id: ID of the publishing peer.
            pc: The peer connection publishing the track.
            track: The media track to publish.

        Returns:
            A stream ID that subscribers can use to receive this track.
        """
        raise NotImplementedError

    async def subscribe(
        self,
        subscriber_id: str,
        pc: WebRTCPeerConnection,
        stream_id: str,
    ) -> None:
        """Subscribe a peer to a published stream.

        Args:
            subscriber_id: ID of the subscribing peer.
            pc: The peer connection to add the track to.
            stream_id: The stream ID returned by ``publish()``.
        """
        raise NotImplementedError

    async def unpublish(self, publisher_id: str) -> None:
        """Remove all streams published by a peer."""
        raise NotImplementedError

    async def list_streams(self) -> list[dict[str, Any]]:
        """List all published streams with metadata."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# In-Memory SFU
# ---------------------------------------------------------------------------


class InMemorySFU(SelectiveForwardingUnit):
    """In-memory Selective Forwarding Unit.

    Relays media tracks between peer connections within the same
    process. Each published track gets a unique stream ID, and
    any number of subscribers can receive a relayed copy.

    The relay creates a new ``MediaStreamTrack`` that reads from
    the original track and writes to each subscriber.

    Usage::

        sfu = InMemorySFU()

        # Publisher (Alice)
        stream_id = await sfu.publish("alice", alice_pc, video_track)

        # Subscriber (Bob)
        await sfu.subscribe("bob", bob_pc, stream_id)
    """

    def __init__(self):
        self._streams: dict[str, dict[str, Any]] = {}
        self._relays: dict[str, Any] = {}

    async def publish(
        self,
        publisher_id: str,
        pc: WebRTCPeerConnection,
        track: Any,
    ) -> str:
        from aiortc import MediaStreamTrack
        from aiortc.contrib.media import MediaRelay

        stream_id = uuid.uuid4().hex[:12]
        relay = MediaRelay()
        self._relays[stream_id] = relay

        kind = track.kind if hasattr(track, "kind") else "unknown"
        self._streams[stream_id] = {
            "id": stream_id,
            "publisher": publisher_id,
            "kind": kind,
            "track": track,
            "relay": relay,
            "subscribers": [],
            "created": time.time(),
        }
        logger.info(
            "sfu: %s published stream %s (%s)", publisher_id, stream_id, kind
        )
        return stream_id

    async def subscribe(
        self,
        subscriber_id: str,
        pc: WebRTCPeerConnection,
        stream_id: str,
    ) -> None:
        stream = self._streams.get(stream_id)
        if stream is None:
            raise ValueError(f"stream {stream_id!r} not found")

        relayed_track = stream["relay"].subscribe(stream["track"])
        if subscriber_id not in stream["subscribers"]:
            stream["subscribers"].append(subscriber_id)

        await pc._pc.addTrack(relayed_track)
        logger.info(
            "sfu: %s subscribed to stream %s", subscriber_id, stream_id
        )

    async def unpublish(self, publisher_id: str) -> None:
        to_remove = [
            sid
            for sid, stream in self._streams.items()
            if stream["publisher"] == publisher_id
        ]
        for sid in to_remove:
            del self._streams[sid]
            self._relays.pop(sid, None)
            logger.info(
                "sfu: removed streams for publisher %s", publisher_id
            )

    async def list_streams(self) -> list[dict[str, Any]]:
        return [
            {
                "id": s["id"],
                "publisher": s["publisher"],
                "kind": s["kind"],
                "subscribers": list(s["subscribers"]),
                "created": s["created"],
            }
            for s in self._streams.values()
        ]


__all__ = [
    "MediaRecorder",
    "MediaFileSink",
    "SelectiveForwardingUnit",
    "InMemorySFU",
]
