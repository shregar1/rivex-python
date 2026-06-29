"""
Unified event bus for WebRTC conference events.

Provides typed event channels that all modules publish to,
enabling decoupled subscribers (logging, metrics, recording,
analytics, dashboards).

Usage::

    bus = EventBus()

    # Subscribe
    bus.on("peer.join", lambda ev: print(ev))
    bus.on("track.added", handler)

    # Publish from anywhere
    bus.emit("peer.join", {"peer_id": "alice", "room": "default"})

    # Typed convenience channels
    bus.peer_joined("alice", room="standup")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


@dataclass
class Event:
    """A single event on the bus."""

    kind: str
    data: dict
    id: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.timestamp:
            self.timestamp = time.time()

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "kind": self.kind,
            "data": self.data,
            "timestamp": self.timestamp,
        })


class EventBus:
    """Typed pub/sub event bus for conference-wide events.

    Standard event kinds:
        "peer.join"       — peer entered the room
        "peer.leave"      — peer left the room
        "peer.kicked"     — peer was kicked
        "track.added"     — media track added
        "track.removed"   — media track removed
        "message.sent"    — data channel message sent
        "message.received" — data channel message received
        "quality.change"  — connection quality changed
        "topology.change" — mesh/SFU topology switched
        "error"           — error condition
        "recording.start" — recording began
        "recording.stop"  — recording ended

    Usage::

        bus = EventBus()

        # Subscribe with optional filter
        bus.on("peer.*", print)

        # Publish
        bus.emit("peer.join", {"peer_id": "alice"})

        # Wait for next event (testing)
        ev = await bus.wait_for("peer.join", timeout=5.0)
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
        self._history: list[Event] = []
        self._max_history: int = 1000
        self._waiters: dict[str, list[asyncio.Future]] = {}
        self._logger = logging.getLogger("rivex.webrtc.event_bus")

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    def on(self, kind: str, handler: Callable) -> Callable:
        """Subscribe to events matching *kind*.

        Supports glob: ``"peer.*"`` matches ``"peer.join"``, ``"peer.leave"``, etc.
        Returns the handler for easy ``remove()``.
        """
        if kind not in self._handlers:
            self._handlers[kind] = []
        self._handlers[kind].append(handler)
        return handler

    def off(self, kind: str, handler: Callable) -> None:
        """Unsubscribe a handler."""
        handlers = self._handlers.get(kind, [])
        if handler in handlers:
            handlers.remove(handler)

    def once(self, kind: str, handler: Callable) -> Callable:
        """Subscribe to the next matching event, then auto-unsubscribe."""
        def wrapper(ev: Event) -> None:
            self.off(kind, wrapper)
            handler(ev)
        return self.on(kind, wrapper)

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def emit(self, kind: str, data: dict) -> Event:
        """Publish an event to all matching subscribers."""
        ev = Event(kind=kind, data=data)
        self._history.append(ev)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        matched = set()
        for pattern, handlers in self._handlers.items():
            if self._matches(kind, pattern):
                for handler in handlers:
                    try:
                        handler(ev)
                    except Exception:
                        self._logger.exception(
                            "Event handler error for %s", kind,
                        )
                matched.add(pattern)

        for pattern, futures in self._waiters.items():
            if self._matches(kind, pattern):
                for fut in futures:
                    if not fut.done():
                        fut.set_result(ev)
                futures.clear()

        return ev

    # ------------------------------------------------------------------
    # Convenience typed publishers
    # ------------------------------------------------------------------

    def peer_joined(self, peer_id: str, room: str = "") -> Event:
        return self.emit("peer.join", {"peer_id": peer_id, "room": room})

    def peer_left(self, peer_id: str, room: str = "") -> Event:
        return self.emit("peer.leave", {"peer_id": peer_id, "room": room})

    def peer_kicked(self, peer_id: str, by: str = "") -> Event:
        return self.emit("peer.kicked", {"peer_id": peer_id, "by": by})

    def track_added(
        self, peer_id: str, track_id: str, kind: str = "",
    ) -> Event:
        return self.emit("track.added", {
            "peer_id": peer_id, "track_id": track_id, "kind": kind,
        })

    def track_removed(self, peer_id: str, track_id: str) -> Event:
        return self.emit("track.removed", {
            "peer_id": peer_id, "track_id": track_id,
        })

    def message_sent(self, peer_id: str, label: str, size: int) -> Event:
        return self.emit("message.sent", {
            "peer_id": peer_id, "label": label, "size": size,
        })

    def message_received(self, peer_id: str, label: str, size: int) -> Event:
        return self.emit("message.received", {
            "peer_id": peer_id, "label": label, "size": size,
        })

    def quality_changed(self, peer_id: str, quality: str) -> Event:
        return self.emit("quality.change", {
            "peer_id": peer_id, "quality": quality,
        })

    def topology_changed(self, from_topo: str, to_topo: str) -> Event:
        return self.emit("topology.change", {
            "from": from_topo, "to": to_topo,
        })

    def error_occurred(self, peer_id: str, message: str) -> Event:
        return self.emit("error", {
            "peer_id": peer_id, "message": message,
        })

    def recording_started(self, session_id: str) -> Event:
        return self.emit("recording.start", {"session_id": session_id})

    def recording_stopped(self, session_id: str) -> Event:
        return self.emit("recording.stop", {"session_id": session_id})

    # ------------------------------------------------------------------
    # Await next event
    # ------------------------------------------------------------------

    async def wait_for(
        self, kind: str, timeout: float = 30.0,
    ) -> Event:
        """Wait for the next event matching *kind*.

        Returns the event, or raises ``asyncio.TimeoutError``.
        """
        future: asyncio.Future = asyncio.Future()
        if kind not in self._waiters:
            self._waiters[kind] = []
        self._waiters[kind].append(future)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._waiters[kind].remove(future)
            raise

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def history(
        self, kind: str | None = None, limit: int = 100,
    ) -> list[Event]:
        """Recent event history, optionally filtered by kind."""
        if kind is None:
            return list(self._history[-limit:])
        return [ev for ev in self._history[-limit:] if self._matches(ev.kind, kind)]

    def clear_history(self) -> None:
        self._history.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _matches(kind: str, pattern: str) -> bool:
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            return kind.startswith(pattern[:-1])
        return kind == pattern


__all__ = [
    "EventBus",
    "Event",
]
