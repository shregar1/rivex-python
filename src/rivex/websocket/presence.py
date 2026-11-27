from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

try:
    import rivex_core as _rc
    HAS_CORE = hasattr(_rc, "PyPresenceTracker")
except ImportError:
    _rc = None  # type: ignore[assignment]
    HAS_CORE = False


class PresenceTracker:
    def __init__(
        self,
        idle_timeout: float = 300.0,
        on_join: Callable | None = None,
        on_leave: Callable | None = None,
    ):
        self._idle_timeout = idle_timeout
        self._on_join = on_join
        self._on_leave = on_leave
        if HAS_CORE:
            self._core = _rc.PyPresenceTracker(idle_timeout)
            self._rooms: dict[str, dict[str, dict[str, Any]]] = {}
            self._connections: dict[int, set[str]] = {}
            self._timestamps: dict[int, float] = {}
        else:
            self._core = None
            self._rooms: dict[str, dict[str, dict[str, Any]]] = {}
            self._connections: dict[int, set[str]] = {}
            self._timestamps: dict[int, float] = {}

    async def track(
        self, connection_id: int, room: str, user_id: str, meta: dict[str, Any] | None = None
    ) -> None:
        """Record a join and broadcast a presence event to the room.

        Adds ``user_id`` to the in-memory membership for ``room`` under
        ``connection_id``, mirroring the change to the native core when
        available, then emits a ``join`` event so other members can update
        their own user lists. If an ``on_join`` callback was supplied at
        construction it is awaited with the same arguments.

        Args:
            connection_id: Numeric id of the WebSocket connection that is
                joining the room.
            room: Logical room identifier the user is joining.
            user_id: Stable user identifier being tracked in the room.
            meta: Optional per-user metadata (display name, avatar, status,
                etc.) echoed in the presence event. Defaults to ``{}`` when
                omitted.
        """
        if room not in self._rooms:
            self._rooms[room] = {}
        self._rooms[room][user_id] = {
            "id": user_id,
            "meta": meta or {},
            "connection_id": connection_id,
            "joined_at": time.time(),
        }
        self._connections.setdefault(connection_id, set()).add(room)
        self._timestamps[connection_id] = time.time()
        if self._core:
            self._core.track(connection_id, room, user_id, json.dumps(meta or {}))
        await self._broadcast_presence(room, "join", user_id, meta)
        if self._on_join:
            await self._on_join(connection_id, room, user_id, meta)

    async def untrack(self, connection_id: int) -> None:
        """Remove every room membership associated with ``connection_id``.

        Looks up all rooms the connection joined, removes the user entries
        belonging to that connection, and broadcasts a ``leave`` presence
        event for each affected room. The native core, when present, mirrors
        the removal there. An ``on_leave`` callback supplied at construction
        time is awaited once per removed user with the original meta.

        Args:
            connection_id: Numeric id of the WebSocket connection whose
                memberships should be cleared. Unknown ids are silently
                ignored.
        """
        rooms = self._connections.pop(connection_id, set())
        self._timestamps.pop(connection_id, None)
        if self._core:
            self._core.untrack(connection_id)
        for room in rooms:
            to_remove = [
                uid
                for uid, info in self._rooms.get(room, {}).items()
                if info.get("connection_id") == connection_id
            ]
            for uid in to_remove:
                info = self._rooms[room].pop(uid, None)
                if info:
                    await self._broadcast_presence(room, "leave", uid, info.get("meta"))
                    if self._on_leave:
                        await self._on_leave(connection_id, room, uid, info.get("meta"))

    async def touch(self, connection_id: int) -> None:
        """Refresh the idle timestamp for ``connection_id``.

        Updates the per-connection ``_timestamps`` entry so
        :meth:`cleanup_idle` does not consider it stale. The native core,
        when present, mirrors the same refresh.

        Args:
            connection_id: Numeric id of the WebSocket connection that just
                sent activity. Unknown ids create a new timestamp entry.
        """
        self._timestamps[connection_id] = time.time()
        if self._core:
            self._core.touch(connection_id)

    def get_room_users(self, room: str) -> list[dict[str, Any]]:
        """Return the user records currently in ``room``.

        Reads from the native core when present and reshapes its tuples into
        the dict shape used throughout this module. In the pure-Python
        fallback, returns the stored presence info verbatim.

        Args:
            room: Logical room identifier to inspect.

        Returns:
            A list of dicts containing ``user_id``, ``connection_id``,
            ``meta`` and ``joined_at``. Empty when ``room`` is unknown or
            has no members.
        """
        if self._core:
            raw = self._core.get_room_users(room)
            return [
                {"user_id": r[0], "connection_id": r[1], "meta": r[2], "joined_at": r[3]}
                for r in raw
            ]
        return list(self._rooms.get(room, {}).values())

    def get_user_rooms(self, user_id: str) -> list[str]:
        """Return the room names that ``user_id`` is currently a member of.

        Delegates to the native core when available; otherwise scans the
        in-memory membership map for rooms whose membership contains the
        given user.

        Args:
            user_id: Stable user identifier to look up.

        Returns:
            A list of room name strings. Empty when the user is not present
            in any room.
        """
        if self._core:
            return self._core.get_user_rooms(user_id)
        return [r for r, users in self._rooms.items() if user_id in users]

    def room_count(self, room: str) -> int:
        """Return the number of distinct users currently in ``room``.

        Delegates to the native core when present; otherwise returns the
        length of the room's membership dict.

        Args:
            room: Logical room identifier to size.

        Returns:
            The number of users in the room, or ``0`` when the room is
            unknown.
        """
        if self._core:
            return self._core.room_count(room)
        return len(self._rooms.get(room, {}))

    def total_connections(self) -> int:
        """Return the number of WebSocket connections the tracker knows about.

        Delegates to the native core when present; otherwise counts entries
        in the ``_connections`` map.

        Returns:
            The number of tracked connections across all rooms.
        """
        if self._core:
            return self._core.total_connections()
        return len(self._connections)

    def active_rooms(self) -> list[str]:
        """Return the names of rooms that currently have at least one user.

        Delegates to the native core when present; otherwise iterates the
        membership map and keeps those whose value dict is non-empty.

        Returns:
            A list of room name strings. Empty when the tracker has no
            active rooms.
        """
        if self._core:
            return self._core.active_rooms()
        return [r for r, users in self._rooms.items() if users]

    async def cleanup_idle(self) -> list[int]:
        """Remove connections that have been quiet longer than ``idle_timeout``.

        Walks the per-connection timestamp map, calls :meth:`untrack` on any
        connection whose last activity is older than the configured timeout,
        and returns the ids that were removed. The native core, when present,
        performs the equivalent scan natively and returns its result.

        Returns:
            The list of connection ids that were reaped for being idle. May
            be empty when nothing has expired.
        """
        if self._core:
            return self._core.cleanup_idle()
        now = time.time()
        stale = [cid for cid, ts in self._timestamps.items() if now - ts > self._idle_timeout]
        for cid in stale:
            await self.untrack(cid)
        return stale

    async def _broadcast_presence(
        self, room: str, event: str, user_id: str, meta: dict[str, Any] | None
    ) -> None:
        """Send a presence event to every member that registered a send hook.

        Serialises the event payload (type, room, user id, meta, and the current
        room roster) and invokes each member's ``_send`` callable, swallowing
        any exceptions so a single broken connection cannot disrupt the rest.
        Used internally by :meth:`track` and :meth:`untrack`.

        Args:
            room: Logical room whose roster should be attached to the event.
            event: ``"join"`` or ``"leave"`` describing what happened.
            user_id: User whose state triggered the event.
            meta: Optional per-user metadata to include in the payload.
        """
        msg = json.dumps(
            {
                "type": "presence",
                "event": event,
                "room": room,
                "user_id": user_id,
                "meta": meta,
                "users": self.get_room_users(room),
            }
        )
        for info in self._rooms.get(room, {}).values():
            if callable(info.get("_send")):
                try:
                    await info["_send"](msg)
                except Exception:
                    pass
