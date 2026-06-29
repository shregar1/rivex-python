from __future__ import annotations

import json
from typing import Any

from rivex.websocket import WebSocket


class ConnectionManager:
    """Manages WebSocket connections with room/broadcast support."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, rooms: list[str] | None = None) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        if rooms:
            for room in rooms:
                self._rooms.setdefault(room, []).append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)
        for room_conns in self._rooms.values():
            if websocket in room_conns:
                room_conns.remove(websocket)

    async def broadcast(self, message: str) -> None:
        for conn in list(self._connections):
            try:
                await conn.send_text(message)
            except Exception:
                self.disconnect(conn)

    async def broadcast_json(self, data: Any) -> None:
        await self.broadcast(json.dumps(data))

    async def send_to_room(self, room: str, message: str) -> None:
        for conn in list(self._rooms.get(room, [])):
            try:
                await conn.send_text(message)
            except Exception:
                self.disconnect(conn)

    async def send_json_to_room(self, room: str, data: Any) -> None:
        await self.send_to_room(room, json.dumps(data))

    def join_room(self, websocket: WebSocket, room: str) -> None:
        self._rooms.setdefault(room, []).append(websocket)

    def leave_room(self, websocket: WebSocket, room: str) -> None:
        conns = self._rooms.get(room, [])
        if websocket in conns:
            conns.remove(websocket)

    @property
    def active_connections(self) -> int:
        return len(self._connections)

    def rooms(self) -> list[str]:
        return list(self._rooms.keys())
