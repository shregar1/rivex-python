"""
Connection pool for reusable WebRTC peer connections.

``PeerConnectionPool`` — manages a pool of ``WebRTCPeerConnection``
objects for reuse across rooms and peers, reducing connection
setup overhead.

Usage::

    pool = PeerConnectionPool(max_size=100, idle_timeout=300)

    # Borrow a connection
    pc = await pool.acquire(config=my_config)

    # Use for a peer
    await do_signaling(pc, peer_id)

    # Return to pool (not close)
    await pool.release(pc)

    # Or discard
    await pool.discard(pc)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from rivex_adapter.webrtc.core import WebRTCPeerConnection, WebRTCConfig, logger


@dataclass
class PoolEntry:
    """A pooled connection and its metadata."""

    pc: WebRTCPeerConnection
    id: str = ""
    created_at: float = 0.0
    last_used: float = 0.0
    borrow_count: int = 0
    config_hash: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = time.time()
        self.last_used = self.created_at


class PeerConnectionPool:
    """Pool of reusable ``WebRTCPeerConnection`` objects.

    Connections are returned to the pool after use, avoiding the
    cost of ICE/DTLS negotiation for subsequent peers.

    Usage::

        pool = PeerConnectionPool(max_size=50)
        pc = await pool.acquire()
        # ... use pc ...
        await pool.release(pc)
    """

    def __init__(
        self,
        max_size: int = 50,
        idle_timeout: float = 300.0,
        max_borrow_count: int = 100,
    ):
        self._max_size = max_size
        self._idle_timeout = idle_timeout
        self._max_borrow_count = max_borrow_count

        self._available: list[PoolEntry] = []
        self._in_use: dict[str, PoolEntry] = {}
        self._lock = asyncio.Lock()
        self._stats = {"created": 0, "reused": 0, "discarded": 0, "timeout": 0}
        self._cleanup_task: asyncio.Task | None = None
        self._logger = logger.getChild("pc_pool")

    async def acquire(
        self, config: WebRTCConfig | None = None,
    ) -> WebRTCPeerConnection:
        """Get a connection from the pool or create a new one."""
        async with self._lock:
            while self._available:
                entry = self._available.pop(0)
                if self._is_expired(entry):
                    self._stats["timeout"] += 1
                    continue
                try:
                    pc = entry.pc
                    state = getattr(pc, "_ice_connection_state", "new")
                    if state in ("failed", "disconnected", "closed"):
                        self._stats["discarded"] += 1
                        continue
                except Exception:
                    self._stats["discarded"] += 1
                    continue

                entry.borrow_count += 1
                entry.last_used = time.time()
                self._in_use[entry.id] = entry
                self._stats["reused"] += 1
                return pc

            # Create new
            pc = WebRTCPeerConnection(config=config or WebRTCConfig())
            entry = PoolEntry(pc=pc)
            self._in_use[entry.id] = entry
            self._stats["created"] += 1
            return pc

    async def release(self, pc: WebRTCPeerConnection) -> None:
        """Return a connection to the pool for reuse."""
        async with self._lock:
            entry = self._find_in_use(pc)
            if entry is None:
                return
            self._in_use.pop(entry.id, None)

            if entry.borrow_count >= self._max_borrow_count:
                self._stats["discarded"] += 1
                await self._close_pc(pc)
                return

            if len(self._available) >= self._max_size:
                self._stats["discarded"] += 1
                await self._close_pc(pc)
                return

            self._available.append(entry)

    async def discard(self, pc: WebRTCPeerConnection) -> None:
        """Remove a connection from the pool and close it."""
        async with self._lock:
            entry = self._find_in_use(pc) or self._find_available(pc)
            if entry:
                self._in_use.pop(entry.id, None)
                if entry in self._available:
                    self._available.remove(entry)
                self._stats["discarded"] += 1
            await self._close_pc(pc)

    async def close(self) -> None:
        """Close all connections in the pool."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            for entry in self._available:
                await self._close_pc(entry.pc)
            for entry in self._in_use.values():
                await self._close_pc(entry.pc)
            self._available.clear()
            self._in_use.clear()

    @property
    def stats(self) -> dict:
        return dict(self._stats, available=len(self._available), in_use=len(self._in_use))

    def start_cleanup(self, interval: float = 60.0) -> None:
        """Periodically evict idle connections."""
        async def _cleanup():
            while True:
                await asyncio.sleep(interval)
                await self._evict_idle()
        self._cleanup_task = asyncio.ensure_future(_cleanup())

    async def _evict_idle(self) -> None:
        async with self._lock:
            now = time.time()
            kept = []
            for entry in self._available:
                if now - entry.last_used > self._idle_timeout:
                    self._stats["timeout"] += 1
                    await self._close_pc(entry.pc)
                else:
                    kept.append(entry)
            self._available = kept

    def _find_in_use(self, pc: WebRTCPeerConnection) -> PoolEntry | None:
        for entry in self._in_use.values():
            if entry.pc is pc:
                return entry
        return None

    def _find_available(self, pc: WebRTCPeerConnection) -> PoolEntry | None:
        for entry in self._available:
            if entry.pc is pc:
                return entry
        return None

    def _is_expired(self, entry: PoolEntry) -> bool:
        return time.time() - entry.last_used > self._idle_timeout

    async def _close_pc(self, pc: WebRTCPeerConnection) -> None:
        try:
            await pc.close()
        except Exception:
            pass


__all__ = [
    "PeerConnectionPool",
    "PoolEntry",
]
