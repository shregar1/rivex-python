"""
Multi-peer connection management.

Provides:
- ``MultiPeerManager`` — manage a group of WebRTCPeerConnection instances
- ``PeerGroup`` — a named group of peer connections for bulk operations

Useful for managing multiple simultaneous outbound connections
(e.g., a broadcaster sending to many viewers).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, WebRTCConfig, logger


class PeerGroup:
    """A named group of peer connections for bulk operations.

    Usage::

        group = PeerGroup("viewers")
        group.add("viewer-1", pc1)
        group.add("viewer-2", pc2)

        await group.broadcast("chat", "Hello everyone!")
        stats = group.get_stats()
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._peers: dict[str, WebRTCPeerConnection] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def add(
        self,
        peer_id: str,
        pc: WebRTCPeerConnection,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a peer connection to the group."""
        self._peers[peer_id] = pc
        if metadata:
            self._metadata[peer_id] = metadata

    def remove(self, peer_id: str) -> WebRTCPeerConnection | None:
        """Remove and return a peer connection."""
        pc = self._peers.pop(peer_id, None)
        self._metadata.pop(peer_id, None)
        return pc

    def get(self, peer_id: str) -> WebRTCPeerConnection | None:
        """Get a peer connection by ID."""
        return self._peers.get(peer_id)

    def get_all(self) -> list[WebRTCPeerConnection]:
        """Get all peer connections."""
        return list(self._peers.values())

    def list_ids(self) -> list[str]:
        """List all peer IDs in the group."""
        return list(self._peers.keys())

    def count(self) -> int:
        """Number of peers in the group."""
        return len(self._peers)

    async def broadcast(self, label: str, data: str | bytes) -> list[str]:
        """Send *data* to all peers on the given data channel.

        Returns a list of peer IDs that failed.
        """
        failed: list[str] = []
        for pid, pc in self._peers.items():
            try:
                await pc.send_data(label, data)
            except Exception:
                failed.append(pid)
        return failed

    async def close_all(self) -> None:
        """Close all peer connections in the group."""
        for pid in list(self._peers.keys()):
            pc = self._peers.pop(pid)
            try:
                await pc.close()
            except Exception:
                pass
        self._metadata.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics for the group."""
        total = self.count()
        by_state: dict[str, int] = {}
        for pc in self._peers.values():
            state = pc.connection_state
            by_state[state] = by_state.get(state, 0) + 1

        return {
            "group": self.name,
            "total": total,
            "by_state": by_state,
            "peer_ids": self.list_ids(),
        }


class MultiPeerManager:
    """Manage multiple simultaneous peer connections.

    Useful for broadcasters (one source, many viewers) or for
    managing multiple signaling connections.

    Usage::

        manager = MultiPeerManager(config=WebRTCConfig())

        # Create a group
        viewers = manager.create_group("viewers")

        # Add peers
        pc = WebRTCPeerConnection(peer_id="viewer-1")
        viewers.add("viewer-1", pc)

        # Bulk operations
        await viewers.broadcast("chat", "Hello!")

    Extensibility:
        Subclass and override ``on_peer_added()`` or
        ``on_peer_removed()`` for custom lifecycle hooks.
    """

    def __init__(self, config: WebRTCConfig | None = None):
        self.config = config or WebRTCConfig()
        self._groups: dict[str, PeerGroup] = {}
        self._on_peer_added: list[Callable[[str, str], None]] = []
        self._on_peer_removed: list[Callable[[str, str], None]] = []
        self._logger = logger.getChild("multi-peer")

    def on_peer_added(self, callback: Callable[[str, str], None]) -> None:
        """Called when a peer is added to a group."""
        self._on_peer_added.append(callback)

    def on_peer_removed(self, callback: Callable[[str, str], None]) -> None:
        """Called when a peer is removed from a group."""
        self._on_peer_removed.append(callback)

    def create_group(self, name: str) -> PeerGroup:
        """Create a new named peer group.

        If the group already exists, returns the existing one.
        """
        if name not in self._groups:
            group = PeerGroup(name)
            self._groups[name] = group
            self._logger.debug("created peer group %r", name)
        return self._groups[name]

    def get_group(self, name: str) -> PeerGroup | None:
        """Get a peer group by name."""
        return self._groups.get(name)

    def remove_group(self, name: str) -> None:
        """Remove a peer group and close all its connections."""
        group = self._groups.pop(name, None)
        if group is not None:
            asyncio.ensure_future(group.close_all())

    def list_groups(self) -> list[str]:
        """List all group names."""
        return list(self._groups.keys())

    def add_peer_to_group(
        self,
        group_name: str,
        peer_id: str,
        pc: WebRTCPeerConnection,
        metadata: dict[str, Any] | None = None,
    ) -> PeerGroup:
        """Add a peer connection to a group (creates group if needed)."""
        group = self.create_group(group_name)
        group.add(peer_id, pc, metadata)
        for cb in self._on_peer_added:
            cb(group_name, peer_id)
        return group

    def remove_peer_from_group(
        self, group_name: str, peer_id: str
    ) -> WebRTCPeerConnection | None:
        """Remove a peer connection from a group."""
        group = self._groups.get(group_name)
        if group is None:
            return None
        pc = group.remove(peer_id)
        if pc is not None:
            for cb in self._on_peer_removed:
                cb(group_name, peer_id)
        return pc

    async def close_all(self) -> None:
        """Close all groups and all peer connections."""
        for name in list(self._groups.keys()):
            self.remove_group(name)

    def get_all_peers(self) -> dict[str, list[str]]:
        """Get all peer IDs organized by group."""
        return {
            name: group.list_ids()
            for name, group in self._groups.items()
        }

    def get_total_peer_count(self) -> int:
        """Total number of peers across all groups."""
        return sum(g.count() for g in self._groups.values())

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate stats across all groups."""
        return {
            "groups": len(self._groups),
            "total_peers": self.get_total_peer_count(),
            "per_group": {
                name: group.get_stats()
                for name, group in self._groups.items()
            },
        }


__all__ = [
    "MultiPeerManager",
    "PeerGroup",
]
