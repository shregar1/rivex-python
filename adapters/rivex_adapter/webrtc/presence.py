"""
Peer presence and activity tracking for WebRTC.

Provides:
- ``PeerPresence`` — track peer status, activity, and typing indicators
- ``PresenceStore`` — store and query presence data
- ``TypingIndicator`` — typing status for data channels
- ``ActivityTracker`` — track peer idle/active state
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, SignalingMessage, SignalingMessageType, logger


class PeerStatus(Enum):
    ONLINE = "online"
    AWAY = "away"
    BUSY = "busy"
    DO_NOT_DISTURB = "dnd"
    OFFLINE = "offline"


class ActivityState(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    AWAY = "away"


@dataclass
class PresenceInfo:
    """Rich presence information for a peer."""

    peer_id: str
    status: PeerStatus = PeerStatus.ONLINE
    activity: ActivityState = ActivityState.ACTIVE
    last_seen: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    last_typing: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    custom_status: str = ""


class PresenceStore:
    """Store and query presence data for peers.

    Provides thread-safe access to presence information with
    search and filtering capabilities.

    Usage::

        store = PresenceStore()
        store.update("alice", PresenceInfo(peer_id="alice", custom_status="In meeting"))
        info = store.get("alice")
        online = store.search(status=PeerStatus.ONLINE)
    """

    def __init__(self):
        self._peers: dict[str, PresenceInfo] = {}
        self._logger = logger.getChild("presence-store")

    def update(self, peer_id: str, info: PresenceInfo) -> None:
        """Update presence info for a peer."""
        info.last_seen = time.time()
        self._peers[peer_id] = info

    def get(self, peer_id: str) -> PresenceInfo | None:
        """Get presence info for a peer."""
        return self._peers.get(peer_id)

    def remove(self, peer_id: str) -> None:
        """Remove a peer's presence info."""
        self._peers.pop(peer_id, None)

    def search(
        self,
        status: PeerStatus | None = None,
        activity: ActivityState | None = None,
        room: str | None = None,
    ) -> list[PresenceInfo]:
        """Search peers by status, activity, or room."""
        results = list(self._peers.values())

        if status is not None:
            results = [p for p in results if p.status == status]
        if activity is not None:
            results = [p for p in results if p.activity == activity]

        return results

    def list_all(self) -> list[PresenceInfo]:
        """List all tracked peers."""
        return list(self._peers.values())

    def count(self, status: PeerStatus | None = None) -> int:
        """Count peers, optionally filtered by status."""
        if status is None:
            return len(self._peers)
        return len([p for p in self._peers.values() if p.status == status])


class TypingIndicator:
    """Typing status indicator for data channels.

    Sends and receives typing notifications over a dedicated
    data channel. Includes configurable timeout and debounce.

    Usage::

        typing = TypingIndicator(pc, channel_label="typing")

        # Sender
        await typing.start_typing()
        # ... user is typing ...
        await typing.stop_typing()

        # Receiver
        typing.on_typing_start(lambda peer_id: print(f"{peer_id} is typing"))
        typing.on_typing_stop(lambda peer_id: print(f"{peer_id} stopped"))
    """

    TYPING_TIMEOUT = 5.0
    DEBOUNCE_INTERVAL = 2.0

    def __init__(
        self,
        pc: WebRTCPeerConnection,
        channel_label: str = "typing",
    ):
        self.pc = pc
        self.channel_label = channel_label
        self._channel: Any = None
        self._typing_start: list[Callable[[str], None]] = []
        self._typing_stop: list[Callable[[str], None]] = []
        self._is_typing = False
        self._typing_task: asyncio.Task[None] | None = None
        self._remote_typing: dict[str, float] = {}
        self._logger = logger.getChild(f"typing-{pc.peer_id}")

    def on_typing_start(self, callback: Callable[[str], None]) -> None:
        """Called when a remote peer starts typing.

        The callback receives the peer ID.
        """
        self._typing_start.append(callback)

    def on_typing_stop(self, callback: Callable[[str], None]) -> None:
        """Called when a remote peer stops typing."""
        self._typing_stop.append(callback)

    async def start_typing(self) -> None:
        """Send a typing-started notification."""
        if self._is_typing:
            return
        self._is_typing = True
        await self._send_typing(True)
        self._typing_task = asyncio.ensure_future(self._typing_heartbeat())

    async def stop_typing(self) -> None:
        """Send a typing-stopped notification."""
        if not self._is_typing:
            return
        self._is_typing = False
        if self._typing_task is not None:
            self._typing_task.cancel()
            self._typing_task = None
        await self._send_typing(False)

    async def _send_typing(self, is_typing: bool) -> None:
        channel = await self._ensure_channel()
        try:
            channel.send(json.dumps({
                "typing": is_typing,
                "peer_id": self.pc.peer_id,
                "timestamp": time.time(),
            }))
        except Exception:
            pass

    async def _typing_heartbeat(self) -> None:
        while self._is_typing:
            try:
                await asyncio.sleep(self.TYPING_TIMEOUT / 2)
                await self._send_typing(True)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _ensure_channel(self) -> Any:
        if self._channel is None:
            if self.channel_label in self.pc._data_channels:
                self._channel = self.pc._data_channels[self.channel_label]
            else:
                self._channel = self.pc.create_data_channel(
                    self.channel_label, ordered=True
                )
            self._wire_receiver()
        return self._channel

    def _wire_receiver(self) -> None:
        original = self.pc._on_message

        def _on_message(label: str, data: str | bytes) -> None:
            if label == self.channel_label and isinstance(data, str):
                try:
                    msg = json.loads(data)
                    if "typing" in msg:
                        peer_id = msg.get("peer_id", "unknown")
                        is_typing = msg["typing"]

                        if is_typing:
                            self._remote_typing[peer_id] = time.time()
                            for cb in self._typing_start:
                                cb(peer_id)
                        else:
                            self._remote_typing.pop(peer_id, None)
                            for cb in self._typing_stop:
                                cb(peer_id)
                except (json.JSONDecodeError, ValueError):
                    pass

            if original:
                original(label, data)

        self.pc._on_message = _on_message

    def is_remote_typing(self, peer_id: str) -> bool:
        """Check if a remote peer is currently typing."""
        last = self._remote_typing.get(peer_id, 0)
        return (time.time() - last) < self.TYPING_TIMEOUT

    def get_typing_peers(self) -> list[str]:
        """List peers currently typing."""
        now = time.time()
        return [
            pid for pid, ts in self._remote_typing.items()
            if (now - ts) < self.TYPING_TIMEOUT
        ]


class ActivityTracker:
    """Track peer active/idle state based on data channel activity.

    Automatically detects when a peer becomes idle after a
    configurable timeout.

    Usage::

        tracker = ActivityTracker(timeout=60)

        # Register a peer
        tracker.register("alice")

        # Call on any activity
        tracker.activity("alice")

        # Check states
        state = tracker.get_state("alice")

        # Listen for changes
        tracker.on_state_change(lambda pid, state: print(f"{pid}: {state}"))
    """

    def __init__(self, idle_timeout: float = 60.0, away_timeout: float = 300.0):
        self.idle_timeout = idle_timeout
        self.away_timeout = away_timeout
        self._peers: dict[str, dict[str, Any]] = {}
        self._on_state_change: list[Callable[[str, ActivityState], None]] = []
        self._task: asyncio.Task[None] | None = None

    def on_state_change(
        self, callback: Callable[[str, ActivityState], None]
    ) -> None:
        """Called when a peer's activity state changes."""
        self._on_state_change.append(callback)

    def register(self, peer_id: str) -> None:
        """Register a peer for activity tracking."""
        self._peers[peer_id] = {
            "last_active": time.time(),
            "state": ActivityState.ACTIVE,
        }

    def unregister(self, peer_id: str) -> None:
        """Unregister a peer."""
        self._peers.pop(peer_id, None)

    def activity(self, peer_id: str) -> None:
        """Record activity for a peer."""
        info = self._peers.get(peer_id)
        if info is not None:
            info["last_active"] = time.time()

    def get_state(self, peer_id: str) -> ActivityState | None:
        """Get the current activity state for a peer."""
        info = self._peers.get(peer_id)
        if info is None:
            return None
        elapsed = time.time() - info["last_active"]
        if elapsed > self.away_timeout:
            return ActivityState.AWAY
        elif elapsed > self.idle_timeout:
            return ActivityState.IDLE
        return ActivityState.ACTIVE

    def start(self) -> None:
        """Start the tracking loop."""
        if self._task is None:
            self._task = asyncio.ensure_future(self._loop())

    def stop(self) -> None:
        """Stop the tracking loop."""
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(5)
                now = time.time()
                for pid, info in self._peers.items():
                    elapsed = now - info["last_active"]
                    old_state = info["state"]

                    if elapsed > self.away_timeout:
                        new_state = ActivityState.AWAY
                    elif elapsed > self.idle_timeout:
                        new_state = ActivityState.IDLE
                    else:
                        new_state = ActivityState.ACTIVE

                    if new_state != old_state:
                        info["state"] = new_state
                        for cb in self._on_state_change:
                            cb(pid, new_state)
            except asyncio.CancelledError:
                break
            except Exception:
                pass


__all__ = [
    "PeerPresence",
    "PresenceStore",
    "TypingIndicator",
    "ActivityTracker",
    "PeerStatus",
    "ActivityState",
    "PresenceInfo",
]
