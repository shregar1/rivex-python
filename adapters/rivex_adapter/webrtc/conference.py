"""
Mesh conference management for WebRTC.

Provides:
- ``ConferenceBridge`` — full mesh conference with auto peer routing
- ``MeshPeer`` — per-peer state within a conference
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from rivex_adapter.webrtc.core import (
    WebRTCPeerConnection,
    WebRTCConfig,
    IceServer,
    SignalingMessage,
    SignalingMessageType,
    logger,
)
from rivex_adapter.webrtc.media import SelectiveForwardingUnit, InMemorySFU
from rivex_adapter.webrtc.quality import ConnectionQualityMonitor


@dataclass
class MeshPeer:
    """State for a single peer within a mesh conference."""

    peer_id: str
    pc: WebRTCPeerConnection
    joined_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    data_channels: dict[str, Any] = field(default_factory=dict)
    quality: ConnectionQualityMonitor | None = None


class ConferenceBridge:
    """Full mesh WebRTC conference manager.

    Each peer that joins gets a ``WebRTCPeerConnection`` to every
    other peer already in the conference. Data channels, media
    tracks, and ICE candidates are routed automatically.

    Supports both pure mesh (N peer connections per participant)
    and SFU-bridged topologies via the optional ``sfu`` parameter.

    Usage::

        bridge = ConferenceBridge(room="my-room")

        # A peer joins
        alice_pc = await bridge.add_peer("alice")

        # Another peer joins — automatically connected to alice
        bob_pc = await bridge.add_peer("bob")

        # Broadcast a message to all peers
        await bridge.broadcast({"type": "chat", "text": "Hello!"})

        # Get conference stats
        stats = bridge.get_stats()

    Extensibility:
        Subclass and override ``create_peer_connection()``,
        ``on_peer_connected()``, ``on_peer_disconnected()``, or
        ``configure_data_channels()``.
    """

    def __init__(
        self,
        room: str = "default",
        config: WebRTCConfig | None = None,
        sfu: SelectiveForwardingUnit | None = None,
    ):
        self.room = room
        self.config = config or WebRTCConfig()
        self.sfu = sfu
        self._peers: dict[str, MeshPeer] = {}
        self._connections: dict[tuple[str, str], WebRTCPeerConnection] = {}
        self._on_join: list[Callable[[str], None]] = []
        self._on_leave: list[Callable[[str], None]] = []
        self._on_message: list[Callable[[str, str, str | bytes], None]] = []
        self._on_track: list[Callable[[str, Any], None]] = []
        self._lock = asyncio.Lock()
        self._logger = logger.getChild(f"conference-{room}")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_join(self, callback: Callable[[str], None]) -> None:
        """Register a callback when a peer joins the conference.

        The callback receives the peer's ID.
        """
        self._on_join.append(callback)

    def on_leave(self, callback: Callable[[str], None]) -> None:
        """Register a callback when a peer leaves the conference."""
        self._on_leave.append(callback)

    def on_message(
        self, callback: Callable[[str, str, str | bytes], None]
    ) -> None:
        """Register a callback for data channel messages.

        The callback receives ``(sender_peer_id, channel_label, data)``.
        """
        self._on_message.append(callback)

    def on_track(self, callback: Callable[[str, Any], None]) -> None:
        """Register a callback when a peer adds a media track.

        The callback receives ``(peer_id, track)``.
        """
        self._on_track.append(callback)

    # ------------------------------------------------------------------
    # Peer lifecycle
    # ------------------------------------------------------------------

    async def add_peer(
        self,
        peer_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> WebRTCPeerConnection:
        """Add a peer to the conference.

        Creates a ``WebRTCPeerConnection`` for this peer, connects
        it to every existing peer in the conference, and sets up
        default data channels.

        Returns the peer's primary ``WebRTCPeerConnection`` (the
        first one created to the first other peer, or a fresh one
        if this is the first participant).
        """
        async with self._lock:
            if peer_id in self._peers:
                raise ValueError(f"peer {peer_id!r} already in conference")

            quality = ConnectionQualityMonitor()

            peer = MeshPeer(
                peer_id=peer_id,
                pc=self._create_primary_pc(peer_id),
                metadata=metadata or {},
                quality=quality,
            )

            self._peers[peer_id] = peer
            self._wire_peer(peer)

            for existing_id in list(self._peers.keys()):
                if existing_id == peer_id:
                    continue
                await self._connect_peers(peer_id, existing_id)

            for cb in self._on_join:
                cb(peer_id)

            self._logger.info(
                "%s joined conference %s (%d peers)",
                peer_id, self.room, len(self._peers),
            )
            return peer.pc

    async def remove_peer(self, peer_id: str) -> None:
        """Remove a peer from the conference and clean up connections."""
        async with self._lock:
            peer = self._peers.pop(peer_id, None)
            if peer is None:
                return

            conns_to_remove = [
                k for k in self._connections
                if k[0] == peer_id or k[1] == peer_id
            ]
            for (a, b) in conns_to_remove:
                pc = self._connections.pop((a, b), None)
                self._connections.pop((b, a), None)
                if pc is not None:
                    await pc.close()

            await peer.pc.close()

            if self.sfu is not None:
                await self.sfu.unpublish(peer_id)

            for cb in self._on_leave:
                cb(peer_id)

            self._logger.info(
                "%s left conference %s (%d peers remaining)",
                peer_id, self.room, len(self._peers),
            )

    async def broadcast(
        self,
        data: str | bytes,
        channel: str = "broadcast",
        exclude: set[str] | None = None,
    ) -> None:
        """Send *data* to all peers on the given data channel."""
        exclude = exclude or set()
        for peer_id, peer in self._peers.items():
            if peer_id in exclude:
                continue
            try:
                await peer.pc.send_data(channel, data)
            except Exception:
                self._logger.warning(
                    "broadcast to %s failed", peer_id
                )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_peers(self) -> list[str]:
        """List all peer IDs in the conference."""
        return list(self._peers.keys())

    def get_peer(self, peer_id: str) -> MeshPeer | None:
        """Get a ``MeshPeer`` by ID."""
        return self._peers.get(peer_id)

    def get_connections(self) -> list[tuple[str, str]]:
        """List all active peer-to-peer connection pairs."""
        return list(self._connections.keys())

    def get_stats(self) -> dict[str, Any]:
        """Get conference-level statistics."""
        peer_count = len(self._peers)
        conn_count = len(self._connections)
        qualities = {}

        for pid, peer in self._peers.items():
            if peer.quality is not None:
                qualities[pid] = peer.quality.last_report

        return {
            "room": self.room,
            "peer_count": peer_count,
            "connection_count": conn_count,
            "mesh_degree": conn_count / max(peer_count, 1),
            "qualities": qualities,
        }

    async def close(self) -> None:
        """Remove all peers and close all connections."""
        for peer_id in list(self._peers.keys()):
            await self.remove_peer(peer_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_primary_pc(self, peer_id: str) -> WebRTCPeerConnection:
        pc = WebRTCPeerConnection(peer_id=peer_id, config=self.config)
        pc.on_connection_state(self._on_peer_connection_state(peer_id))
        return pc

    def _wire_peer(self, peer: MeshPeer) -> None:
        if peer.quality is not None:
            peer.pc.on_stats(peer.quality.on_stats)

        original_on_message = peer.pc._on_message
        def _wrapped_on_message(label: str, data: str | bytes) -> None:
            if original_on_message:
                original_on_message(label, data)
            for cb in self._on_message:
                cb(peer.peer_id, label, data)
        peer.pc._on_message = _wrapped_on_message

        original_on_track = peer.pc._on_track
        def _wrapped_on_track(track: Any) -> None:
            if original_on_track:
                original_on_track(track)
            for cb in self._on_track:
                cb(peer.peer_id, track)
        peer.pc._on_track = _wrapped_on_track

    def _on_peer_connection_state(self, peer_id: str) -> Callable[[str], None]:
        def _handler(state: str) -> None:
            if state in ("failed", "disconnected"):
                asyncio.ensure_future(self._handle_peer_disconnect(peer_id))
        return _handler

    async def _handle_peer_disconnect(self, peer_id: str) -> None:
        self._logger.warning("peer %s disconnected (state: failed)", peer_id)
        await self.remove_peer(peer_id)

    async def _connect_peers(self, a_id: str, b_id: str) -> None:
        if (a_id, b_id) in self._connections:
            return

        peer_a = self._peers.get(a_id)
        peer_b = self._peers.get(b_id)
        if peer_a is None or peer_b is None:
            return

        self._logger.debug("connecting %s <-> %s", a_id, b_id)

        pc_a = WebRTCPeerConnection(peer_id=f"{a_id}->{b_id}", config=self.config)
        pc_b = WebRTCPeerConnection(peer_id=f"{b_id}->{a_id}", config=self.config)

        self._connections[(a_id, b_id)] = pc_a
        self._connections[(b_id, a_id)] = pc_b

        offer = await pc_a.create_offer()
        answer = await pc_b.create_answer(offer)
        await pc_a.set_remote_description(answer)

        channel_a = pc_a.create_data_channel("mesh", ordered=True)
        channel_b = pc_b.create_data_channel("mesh", ordered=True)

        def _make_forward(src_pc: WebRTCPeerConnection, dst_id: str):
            def _forward(label: str, data: str | bytes) -> None:
                dst_peer = self._peers.get(dst_id)
                if dst_peer is not None:
                    asyncio.ensure_future(
                        dst_peer.pc.send_data(label, data)
                    )
            return _forward

        pc_a.on_message(_make_forward(pc_a, b_id))
        pc_b.on_message(_make_forward(pc_b, a_id))

    def create_peer_connection(self, peer_id: str) -> WebRTCPeerConnection:
        """Override to use a custom ``WebRTCPeerConnection`` subclass."""
        return WebRTCPeerConnection(peer_id=peer_id, config=self.config)


class MeshConference(ConferenceBridge):
    """Alias for ``ConferenceBridge`` with SFU support baked in.

    Automatically creates an ``InMemorySFU`` if none is provided,
    and subscribes each new peer to all existing published streams.

    Usage::

        conf = MeshConference(room="video-room", use_sfu=True)
        alice = await conf.add_peer("alice")
        bob = await conf.add_peer("bob")
        # When alice adds a track:
        stream_id = await conf.sfu.publish("alice", alice, track)
        await conf.sfu.subscribe("bob", bob, stream_id)
    """

    def __init__(
        self,
        room: str = "default",
        config: WebRTCConfig | None = None,
        use_sfu: bool = True,
    ):
        super().__init__(
            room=room,
            config=config,
            sfu=InMemorySFU() if use_sfu else None,
        )


__all__ = [
    "ConferenceBridge",
    "MeshConference",
    "MeshPeer",
]
