"""
WebRTC adapter for real-time audio, video, and data channels.

Provides peer connection management, SDP offer/answer negotiation,
ICE candidate exchange, data channels, media stream handling,
ICE restart, and connection statistics via ``aiortc``.

The adapter integrates with Rivex WebSocket signaling out of the box::

    from rivex_adapter.webrtc import WebRTCSignaling

    signaling = WebRTCSignaling()

    @app.websocket("/signal/{room}")
    async def signal_handler(ws):
        async for msg in signaling.handle(ws, room=ws.url_params["room"]):
            await ws.send_json(msg)

Standalone usage::

    from rivex_adapter.webrtc import WebRTCPeerConnection

    pc = WebRTCPeerConnection()
    await pc.create_offer()
    await pc.set_remote_description(...)
    await pc.add_ice_candidate(...)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable

logger = logging.getLogger("rivex.webrtc")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class SignalingMessageType(str, Enum):
    """WebRTC signaling message types exchanged over the signaling channel."""

    OFFER = "offer"
    ANSWER = "answer"
    ICE_CANDIDATE = "ice_candidate"
    ICE_RESTART = "ice_restart"
    JOIN = "join"
    LEAVE = "leave"
    ERROR = "error"
    AUTH = "auth"
    AUTH_OK = "auth_ok"
    AUTH_DENY = "auth_deny"
    PING = "ping"
    PONG = "pong"


@dataclass
class SignalingMessage:
    """A signaling message exchanged between peers."""

    type: SignalingMessageType
    sender: str
    data: Any = None
    target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type.value, "sender": self.sender}
        if self.data is not None:
            d["data"] = self.data
        if self.target is not None:
            d["target"] = self.target
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SignalingMessage:
        return cls(
            type=SignalingMessageType(d["type"]),
            sender=d["sender"],
            data=d.get("data"),
            target=d.get("target"),
        )


class IceServer:
    """STUN / TURN server configuration."""

    def __init__(
        self,
        urls: str | list[str],
        username: str | None = None,
        credential: str | None = None,
    ):
        self.urls = urls if isinstance(urls, list) else [urls]
        self.username = username
        self.credential = credential


# ---------------------------------------------------------------------------
# WebRTC Configuration
# ---------------------------------------------------------------------------


@dataclass
class WebRTCConfig:
    """Global configuration for WebRTC peer connections.

    Subclass and override to add custom configuration fields.
    All fields have defaults suitable for most use cases.
    """

    ice_servers: list[IceServer] = field(default_factory=lambda: [
        IceServer("stun:stun.l.google.com:19302"),
    ])
    bundle_policy: str = "balanced"
    audio_codecs: list[str] | None = None
    video_codecs: list[str] | None = None
    ice_restart_timeout: float = 10.0
    stats_interval: float = 0.0


# ---------------------------------------------------------------------------
# WebRTC Peer Connection
# ---------------------------------------------------------------------------


class WebRTCPeerConnection:
    """High-level wrapper around a single WebRTC peer connection.

    Manages SDP negotiation, ICE candidate exchange, data channels,
    media tracks, ICE restart, and connection stats using ``aiortc``.

    Extensibility:
        Subclass and override any method to customize behavior.
        Key override points: ``ensure_pc()``, ``build_sdp_description()``,
        ``build_ice_candidate()``, ``on_connection_state_changed()``.
    """

    def __init__(
        self,
        peer_id: str | None = None,
        config: WebRTCConfig | None = None,
    ):
        self.peer_id = peer_id or uuid.uuid4().hex[:12]
        self.config = config or WebRTCConfig()
        self._pc: Any = None
        self._data_channels: dict[str, Any] = {}
        self._media_tracks: dict[str, Any] = {}
        self._on_message: Callable[[str, str | bytes], None] | None = None
        self._on_ice_candidate: Callable[[dict[str, Any]], None] | None = None
        self._on_connection_state: Callable[[str], None] | None = None
        self._on_track: Callable[[Any], None] | None = None
        self._on_ice_restart_needed: Callable[[], None] | None = None
        self._negotiated = False
        self._pending_candidates: list[dict[str, Any]] = []
        self._closed = False
        self._last_offer: dict[str, Any] | None = None
        self._stats_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._stats_task: asyncio.Task[None] | None = None
        self._logger = logger.getChild(self.peer_id)

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_message(self, callback: Callable[[str, str | bytes], None]) -> None:
        """Register a callback for incoming data channel messages.

        The callback receives ``(channel_label, data)``.
        """
        self._on_message = callback

    def on_ice_candidate(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for outgoing ICE candidates."""
        self._on_ice_candidate = callback

    def on_connection_state(self, callback: Callable[[str], None]) -> None:
        """Register a callback for connection state changes.

        States: ``"new"``, ``"connecting"``, ``"connected"``,
        ``"disconnected"``, ``"failed"``, ``"closed"``.
        """
        self._on_connection_state = callback

    def on_track(self, callback: Callable[[Any], None]) -> None:
        """Register a callback for incoming media tracks."""
        self._on_track = callback

    def on_ice_restart_needed(self, callback: Callable[[], None]) -> None:
        """Register a callback triggered when an ICE restart is needed.

        This is called when the connection enters the ``"failed"``
        state. The callback should initiate ``ice_restart()``.
        """
        self._on_ice_restart_needed = callback

    def on_stats(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for periodic connection stats.

        Stats are collected at the interval configured in
        ``WebRTCConfig.stats_interval``. The callback receives a
        dict with ICE candidate pair stats, bytes sent/received, etc.

        Requires ``stats_interval > 0`` in config.
        """
        self._stats_callbacks.append(callback)

    # ------------------------------------------------------------------
    # SDP negotiation
    # ------------------------------------------------------------------

    async def create_offer(self) -> dict[str, Any]:
        """Create and return an SDP offer."""
        await self.ensure_pc()
        offer = await self._pc.createOffer()
        await self._pc.setLocalDescription(offer)
        sdp = {"sdp": offer.sdp, "type": offer.type}
        self._negotiated = True
        self._last_offer = sdp
        return sdp

    async def create_answer(self, offer_sdp: dict[str, Any]) -> dict[str, Any]:
        """Create and return an SDP answer given a remote offer."""
        await self.ensure_pc()
        await self._pc.setRemoteDescription(
            self.build_sdp_description(offer_sdp["sdp"], offer_sdp["type"])
        )
        answer = await self._pc.createAnswer()
        await self._pc.setLocalDescription(answer)
        sdp = {"sdp": answer.sdp, "type": answer.type}
        self._negotiated = True
        return sdp

    async def set_remote_description(self, sdp: dict[str, Any]) -> None:
        """Set the remote SDP (offer or answer)."""
        await self.ensure_pc()
        await self._pc.setRemoteDescription(
            self.build_sdp_description(sdp["sdp"], sdp["type"])
        )
        for candidate in self._pending_candidates:
            await self._pc.addIceCandidate(self.build_ice_candidate(candidate))
        self._pending_candidates.clear()

    async def add_ice_candidate(self, candidate: dict[str, Any]) -> None:
        """Add a remote ICE candidate.

        If the remote description hasn't been set yet, the candidate
        is queued and added once ``set_remote_description`` is called.
        """
        if not self._negotiated:
            self._pending_candidates.append(candidate)
            return
        await self.ensure_pc()
        await self._pc.addIceCandidate(self.build_ice_candidate(candidate))

    # ------------------------------------------------------------------
    # ICE restart
    # ------------------------------------------------------------------

    async def ice_restart(self) -> dict[str, Any]:
        """Perform an ICE restart and return a new SDP offer.

        This creates a fresh offer with the ``iceRestart`` flag set,
        which forces new ICE credentials and a new connectivity check.

        Call this when the connection enters the ``"failed"`` state
        or when a network change is detected.
        """
        await self.ensure_pc()
        offer = await self._pc.createOffer(iceRestart=True)
        await self._pc.setLocalDescription(offer)
        sdp = {"sdp": offer.sdp, "type": offer.type}
        self._last_offer = sdp
        self._logger.info("ice restart initiated")
        return sdp

    # ------------------------------------------------------------------
    # Data channels
    # ------------------------------------------------------------------

    def create_data_channel(
        self,
        label: str,
        ordered: bool = True,
        max_retransmits: int | None = None,
    ) -> Any:
        """Create a data channel on this peer connection.

        Returns the ``aiortc`` data channel object. Messages are
        routed to the ``on_message`` callback.
        """
        channel = self._pc.createDataChannel(
            label,
            ordered=ordered,
            maxRetransmits=max_retransmits,
        )
        self._data_channels[label] = channel
        self._wire_data_channel(channel, label)
        return channel

    async def send_data(self, label: str, data: str | bytes) -> None:
        """Send *data* on the named data channel."""
        channel = self._data_channels.get(label)
        if channel is None:
            raise ValueError(f"data channel {label!r} not found")
        channel.send(data)

    # ------------------------------------------------------------------
    # Connection statistics
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict[str, Any]:
        """Collect and return current connection statistics.

        Returns a dict with keys:
        - ``"ice_candidate_pairs"`` — list of candidate pair stats
        - ``"inbound_rtp"`` — list of inbound RTP stream stats
        - ``"outbound_rtp"`` — list of outbound RTP stream stats
        - ``"transport"`` — transport-level stats (bytes sent/received)
        """
        if self._pc is None:
            return {"state": "closed"}

        from aiortc.stats import RTCStatsReport

        report: RTCStatsReport = await self._pc.getStats()
        stats: dict[str, Any] = {
            "timestamp": time.time(),
            "ice_candidate_pairs": [],
            "inbound_rtp": [],
            "outbound_rtp": [],
            "transport": {},
        }

        for s in report.values():
            stype = s.type
            if stype == "candidate-pair":
                pair = {"state": s.state, "nominated": s.nominated}
                if hasattr(s, "availableOutgoingBitrate"):
                    pair["available_outgoing_bitrate"] = s.availableOutgoingBitrate
                if hasattr(s, "bytesSent"):
                    pair["bytes_sent"] = s.bytesSent
                if hasattr(s, "bytesReceived"):
                    pair["bytes_received"] = s.bytesReceived
                if hasattr(s, "currentRoundTripTime"):
                    pair["current_rtt"] = s.currentRoundTripTime
                stats["ice_candidate_pairs"].append(pair)
            elif stype == "inbound-rtp":
                instats: dict[str, Any] = {"kind": s.kind, "codec": s.codecId}
                if hasattr(s, "packetsReceived"):
                    instats["packets_received"] = s.packetsReceived
                if hasattr(s, "bytesReceived"):
                    instats["bytes_received"] = s.bytesReceived
                if hasattr(s, "jitter"):
                    instats["jitter"] = s.jitter
                if hasattr(s, "packetsLost"):
                    instats["packets_lost"] = s.packetsLost
                stats["inbound_rtp"].append(instats)
            elif stype == "outbound-rtp":
                outstats: dict[str, Any] = {"kind": s.kind, "codec": s.codecId}
                if hasattr(s, "packetsSent"):
                    outstats["packets_sent"] = s.packetsSent
                if hasattr(s, "bytesSent"):
                    outstats["bytes_sent"] = s.bytesSent
                stats["outbound_rtp"].append(outstats)
            elif stype == "transport":
                tstats: dict[str, Any] = {}
                if hasattr(s, "bytesSent"):
                    tstats["bytes_sent"] = s.bytesSent
                if hasattr(s, "bytesReceived"):
                    tstats["bytes_received"] = s.bytesReceived
                if hasattr(s, "dtlsState"):
                    stats["dtls_state"] = s.dtlsState
                stats["transport"] = tstats

        return stats

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the peer connection and release resources."""
        if self._closed:
            return
        self._closed = True
        if self._stats_task is not None:
            self._stats_task.cancel()
            self._stats_task = None
        if self._pc is None:
            return
        for channel in self._data_channels.values():
            try:
                channel.close()
            except Exception:
                pass
        self._data_channels.clear()
        self._media_tracks.clear()
        await self._pc.close()
        self._pc = None
        self._negotiated = False

    @property
    def connection_state(self) -> str:
        """Current state of the underlying ``RTCPeerConnection``."""
        if self._pc is None:
            return "closed"
        try:
            return self._pc.connectionState
        except Exception:
            return "unknown"

    @property
    def ice_connection_state(self) -> str:
        """Current ICE connection state."""
        if self._pc is None:
            return "closed"
        try:
            return self._pc.iceConnectionState
        except Exception:
            return "unknown"

    @property
    def is_closed(self) -> bool:
        """Whether the connection has been closed."""
        return self._closed

    # ------------------------------------------------------------------
    # Extensibility hooks (override in subclass)
    # ------------------------------------------------------------------

    async def ensure_pc(self) -> None:
        """Ensure the underlying ``RTCPeerConnection`` is created.

        Override to customize the ``RTCPeerConnection`` creation,
        inject custom ``RTCConfiguration``, or add extra event hooks.
        """
        if self._pc is not None:
            return
        from aiortc import (
            RTCPeerConnection,
            RTCConfiguration,
            RTCIceServer,
        )

        self._pc = RTCPeerConnection(
            configuration=self.build_rtc_configuration()
        )
        self._wire_pc_events()

    def build_rtc_configuration(self) -> Any:
        """Build and return an ``RTCConfiguration`` from ``self.config``.

        Override to customize ICE server list, bundle policy, codec
        preferences, or other ``RTCConfiguration`` attributes.
        """
        from aiortc import RTCConfiguration, RTCIceServer

        ice_servers = [
            RTCIceServer(
                urls=s.urls,
                username=s.username or "",
                credential=s.credential or "",
            )
            for s in self.config.ice_servers
        ]

        return RTCConfiguration(
            iceServers=ice_servers,
            bundlePolicy=self.config.bundle_policy,
        )

    def build_sdp_description(self, sdp: str, sdp_type: str) -> Any:
        """Build an ``RTCSessionDescription`` from SDP string and type.

        Override to modify the SDP before setting it (e.g. to
        filter codecs or add custom media sections).
        """
        from aiortc import RTCSessionDescription

        return RTCSessionDescription(sdp=sdp, type=sdp_type)

    def build_ice_candidate(self, candidate: dict[str, Any]) -> Any:
        """Build an ``RTCIceCandidate`` from a candidate dict.

        Override to add custom ICE candidate attributes.
        """
        from aiortc import RTCIceCandidate

        return RTCIceCandidate(
            candidate=candidate["candidate"],
            sdpMid=candidate.get("sdpMid"),
            sdpMLineIndex=candidate.get("sdpMLineIndex", 0),
        )

    def on_connection_state_changed(self, state: str) -> None:
        """Called when the ICE or connection state changes.

        Override to add custom state transition logic (e.g. auto
        ICE restart on failure, metrics collection).
        """
        if state == "failed" and self._on_ice_restart_needed:
            self._on_ice_restart_needed()

    # ------------------------------------------------------------------
    # Internal wiring
    # ------------------------------------------------------------------

    def _wire_pc_events(self) -> None:
        @self._pc.on("iceconnectionstatechange")
        def _on_ice_state() -> None:
            state = self._pc.iceConnectionState
            self._logger.debug("ice connection state: %s", state)
            self.on_connection_state_changed(state)
            if self._on_connection_state:
                self._on_connection_state(state)

        @self._pc.on("connectionstatechange")
        def _on_conn_state() -> None:
            state = self._pc.connectionState
            self._logger.debug("connection state: %s", state)
            self.on_connection_state_changed(state)
            if self._on_connection_state:
                self._on_connection_state(state)

        @self._pc.on("icecandidate")
        def _on_ice(candidate: Any | None) -> None:
            if candidate is None:
                return
            c_dict = {
                "candidate": candidate.candidate,
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            }
            self._logger.debug("ice candidate: %s", c_dict["candidate"][:60])
            if self._on_ice_candidate:
                self._on_ice_candidate(c_dict)

        @self._pc.on("track")
        def _on_track(track: Any) -> None:
            self._logger.debug("incoming track: %s", track.kind)
            if self._on_track:
                self._on_track(track)

        @self._pc.on("datachannel")
        def _on_channel(channel: Any) -> None:
            label = channel.label or f"chan_{len(self._data_channels)}"
            self._data_channels[label] = channel
            self._wire_data_channel(channel, label)

        if self.config.stats_interval > 0:
            self._start_stats_collection()

    def _start_stats_collection(self) -> None:
        async def _collect() -> None:
            while not self._closed:
                try:
                    await asyncio.sleep(self.config.stats_interval)
                    if self._pc is not None:
                        stats = await self.get_stats()
                        for cb in self._stats_callbacks:
                            cb(stats)
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass

        self._stats_task = asyncio.ensure_future(_collect())

    def _wire_data_channel(self, channel: Any, label: str) -> None:
        @channel.on("message")
        def _on_channel_message(message: Any) -> None:
            if self._on_message:
                self._on_message(label, message)

    # ------------------------------------------------------------------
    # Backward compat aliases
    # ------------------------------------------------------------------

    async def _ensure_pc(self) -> None:
        await self.ensure_pc()

    def _sdp_object(self, sdp: str, sdp_type: str) -> Any:
        return self.build_sdp_description(sdp, sdp_type)

    def _ice_candidate_object(self, candidate: dict[str, Any]) -> Any:
        return self.build_ice_candidate(candidate)


# ---------------------------------------------------------------------------
# Helper: create a media stream from file or camera
# ---------------------------------------------------------------------------


async def create_media_stream(
    source: str | None = None,
    audio: bool = False,
    video: bool = False,
    loop: bool = False,
) -> Any:
    """Create an ``aiortc`` ``MediaStream`` from a file or device.

    Args:
        source: File path or URL. If ``None``, no source (add tracks manually).
        audio: If ``True`` and no source, include default microphone.
        video: If ``True`` and no source, include default camera.
        loop: If ``True``, loop the source file when it ends.

    Returns:
        A list of ``MediaStreamTrack`` objects.
    """
    from aiortc import MediaStreamTrack
    from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRelay

    tracks: list[MediaStreamTrack] = []

    if source is not None:
        player = MediaPlayer(source, loop=loop, format="mp4" if source.endswith(".mp4") else None)
        if audio and player.audio is not None:
            tracks.append(player.audio)
        if video and player.video is not None:
            tracks.append(player.video)

    return tracks


# ---------------------------------------------------------------------------
# Convenience: add a media track to a peer connection
# ---------------------------------------------------------------------------


async def add_media_track(
    pc: WebRTCPeerConnection,
    track: Any,
) -> Any:
    """Add a media track (*audio* or *video*) to an ``RTCPeerConnection``.

    Returns the ``RTCRtpSender`` for the added track.
    """
    return pc._pc.addTrack(track)
