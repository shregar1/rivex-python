"""
Dynamic topology switching for WebRTC conferences.

Supports:
- **Mesh** — every peer connects to every other peer (full mesh)
- **SFU** — all peers connect to a central Selective Forwarding Unit
- **Hybrid** — some peers in mesh, some via SFU

``TopologyManager`` switches between topologies mid-session,
migrating peer connections smoothly.

Usage::

    mgr = TopologyManager(bridge=conference_bridge)

    # Start in mesh mode
    await mgr.set_topology("mesh")

    # Switch to SFU mid-call
    await mgr.set_topology("sfu")

    # Get current topology
    print(mgr.current_topology)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rivex_adapter.webrtc.conference import ConferenceBridge
from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger


class Topology(str, Enum):
    MESH = "mesh"
    SFU = "sfu"
    HYBRID = "hybrid"


@dataclass
class TopologyChange:
    """Records a topology switch event."""

    from_topology: Topology | None
    to_topology: Topology
    timestamp: float = field(default_factory=time.time)
    peer_count: int = 0
    duration_ms: float = 0.0
    success: bool = True


class TopologyManager:
    """Dynamic topology manager for WebRTC conferences.

    Switches between mesh and SFU topologies at runtime, migrating
    all peer connections.

    Usage::

        bridge = ConferenceBridge(room="my-room")
        mgr = TopologyManager(bridge, sfu=InMemorySFU())

        await mgr.set_topology("mesh")
        # ... add peers ...

        await mgr.set_topology("sfu")
        # ... peers are now connected through SFU ...
    """

    def __init__(
        self,
        bridge: ConferenceBridge,
        sfu: Any = None,
    ):
        self.bridge = bridge
        self._sfu = sfu
        self._current: Topology | None = None
        self._changes: list[TopologyChange] = []
        self._on_change: list[Callable] = []
        self._logger = logger.getChild(f"topology-{bridge.room}")

    @property
    def current_topology(self) -> Topology | None:
        return self._current

    @property
    def change_history(self) -> list[TopologyChange]:
        return list(self._changes)

    def on_change(self, callback: Callable) -> None:
        """Register a callback for topology changes.

        The callback receives ``(from_topo, to_topo)``.
        """
        self._on_change.append(callback)

    async def set_topology(self, topology: str | Topology) -> TopologyChange:
        """Switch to a different topology.

        Args:
            topology: One of ``"mesh"``, ``"sfu"``, or ``"hybrid"``.

        Returns:
            A ``TopologyChange`` record.
        """
        if isinstance(topology, str):
            topology = Topology(topology)

        old = self._current
        if old == topology:
            return TopologyChange(
                from_topology=old, to_topology=topology,
                peer_count=len(self.bridge._peers),
            )

        start = time.monotonic()
        change = TopologyChange(
            from_topology=old,
            to_topology=topology,
            peer_count=len(self.bridge._peers),
        )

        try:
            if topology == Topology.MESH:
                await self._switch_to_mesh()
            elif topology == Topology.SFU:
                await self._switch_to_sfu()
            elif topology == Topology.HYBRID:
                await self._switch_to_hybrid()

            self._current = topology
            change.duration_ms = (time.monotonic() - start) * 1000.0
            change.success = True
        except Exception as e:
            self._logger.exception("topology switch to %s failed", topology)
            change.success = False
            change.duration_ms = (time.monotonic() - start) * 1000.0

        self._changes.append(change)

        for cb in self._on_change:
            try:
                cb(old, topology)
            except Exception:
                self._logger.exception("on_change handler error")

        return change

    async def _switch_to_mesh(self) -> None:
        """Convert SFU connections to full mesh."""
        peer_ids = list(self.bridge._peers.keys())
        for i, pid_a in enumerate(peer_ids):
            for pid_b in peer_ids[i + 1:]:
                key = (pid_a, pid_b)
                if key not in self.bridge._connections:
                    pc_a = self.bridge._peers[pid_a].pc
                    pc_b = self.bridge._peers[pid_b].pc
                    # Create peer connection between the two peers
                    pc = WebRTCPeerConnection()
                    self._forward_tracks(pc_a, pc)
                    self._forward_tracks(pc_b, pc)
                    self.bridge._connections[key] = pc
        self._logger.info(
            "Switched to mesh: %d peers, %d connections",
            len(peer_ids), len(self.bridge._connections),
        )

    async def _switch_to_sfu(self) -> None:
        """Convert mesh connections to SFU."""
        if self._sfu is None:
            raise ValueError("SFU not configured — set sfu= on init")
        for key in list(self.bridge._connections.keys()):
            if key[0] != "sfu":
                pc = self.bridge._connections.pop(key, None)
                if pc:
                    await pc.close()
        # Reconnect each peer through the SFU
        for peer_id in self.bridge._peers:
            pc = self.bridge._peers[peer_id].pc
            # Route tracks through SFU
            sfu_pc = WebRTCPeerConnection()
            self._sfu.add_peer(peer_id, sfu_pc)
            self._forward_tracks(pc, sfu_pc)
            self.bridge._connections[("sfu", peer_id)] = sfu_pc
        self._logger.info(
            "Switched to SFU: %d peers routed through SFU",
            len(self.bridge._peers),
        )

    async def _switch_to_hybrid(self) -> None:
        """Hybrid: some peers mesh, some via SFU.

        The first *N* peers mesh; the rest connect via SFU.
        """
        peer_ids = list(self.bridge._peers.keys())
        if len(peer_ids) < 3:
            await self._switch_to_mesh()
            return

        mesh_count = max(1, len(peer_ids) // 2)
        mesh_peers = peer_ids[:mesh_count]
        sfu_peers = peer_ids[mesh_count:]

        # Mesh among mesh_peers
        for i, pid_a in enumerate(mesh_peers):
            for pid_b in mesh_peers[i + 1:]:
                key = (pid_a, pid_b)
                if key not in self.bridge._connections:
                    pc = WebRTCPeerConnection()
                    self._forward_tracks(
                        self.bridge._peers[pid_a].pc, pc,
                    )
                    self._forward_tracks(
                        self.bridge._peers[pid_b].pc, pc,
                    )
                    self.bridge._connections[key] = pc

        # SFU for the rest
        if self._sfu and sfu_peers:
            for pid in sfu_peers:
                pc = self.bridge._peers[pid].pc
                sfu_pc = WebRTCPeerConnection()
                self._sfu.add_peer(pid, sfu_pc)
                self._forward_tracks(pc, sfu_pc)
                self.bridge._connections[("sfu", pid)] = sfu_pc

        self._logger.info(
            "Switched to hybrid: %d mesh + %d SFU",
            len(mesh_peers), len(sfu_peers),
        )

    def _forward_tracks(
        self, source_pc: WebRTCPeerConnection, target_pc: WebRTCPeerConnection,
    ) -> None:
        for track in getattr(source_pc, "_tracks", []):
            try:
                target_pc.add_track(track)
            except Exception:
                pass


# Convenience alias
Callable = Any


__all__ = [
    "Topology",
    "TopologyChange",
    "TopologyManager",
]
