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
        self._timestamps[connection_id] = time.time()
        if self._core:
            self._core.touch(connection_id)

    def get_room_users(self, room: str) -> list[dict[str, Any]]:
        if self._core:
            raw = self._core.get_room_users(room)
            return [
                {"user_id": r[0], "connection_id": r[1], "meta": r[2], "joined_at": r[3]}
                for r in raw
            ]
        return list(self._rooms.get(room, {}).values())

    def get_user_rooms(self, user_id: str) -> list[str]:
        if self._core:
            return self._core.get_user_rooms(user_id)
        return [r for r, users in self._rooms.items() if user_id in users]

    def room_count(self, room: str) -> int:
        if self._core:
            return self._core.room_count(room)
        return len(self._rooms.get(room, {}))

    def total_connections(self) -> int:
        if self._core:
            return self._core.total_connections()
        return len(self._connections)

    def active_rooms(self) -> list[str]:
        if self._core:
            return self._core.active_rooms()
        return [r for r, users in self._rooms.items() if users]

    async def cleanup_idle(self) -> list[int]:
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
