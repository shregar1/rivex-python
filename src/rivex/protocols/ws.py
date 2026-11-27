from __future__ import annotations

import json
from typing import Any

from rivex.protocols.websocket import WebSocket


class ConnectionManager:
    """Manages WebSocket connections with room/broadcast support."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, rooms: list[str] | None = None) -> None:
        """Accept ``websocket`` and register it for broadcast and room delivery.

        Calls ``websocket.accept()`` to complete the WebSocket handshake
        and appends the connection to the global list. When ``rooms``
        is supplied, the connection is also added to each named room so
        future :meth:`send_to_room` calls reach it.

        Args:
            websocket: The connection to register.
            rooms: Optional list of room names to join on connect.
        """
        await websocket.accept()
        self._connections.append(websocket)
        if rooms:
            for room in rooms:
                self._rooms.setdefault(room, []).append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove ``websocket`` from the broadcast list and every room.

        Args:
            websocket: The connection to drop. Missing entries in
                either the broadcast list or the room maps are ignored
                so the call is safe even when invoked more than once
                for the same socket.
        """
        if websocket in self._connections:
            self._connections.remove(websocket)
        for room_conns in self._rooms.values():
            if websocket in room_conns:
                room_conns.remove(websocket)

    async def broadcast(self, message: str) -> None:
        """Send ``message`` to every currently connected client.

        Iterates a snapshot of the connection list so a failed send
        can safely call :meth:`disconnect` without breaking iteration.
        Sockets that raise are dropped from the manager.

        Args:
            message: Text payload to deliver to every client.
        """
        for conn in list(self._connections):
            try:
                await conn.send_text(message)
            except Exception:
                self.disconnect(conn)

    async def broadcast_json(self, data: Any) -> None:
        """Serialize ``data`` to JSON and broadcast it to every client.

        Args:
            data: Any value accepted by ``json.dumps`` — typically a
                dict or list.
        """
        await self.broadcast(json.dumps(data))

    async def send_to_room(self, room: str, message: str) -> None:
        """Send ``message`` to every connection that has joined ``room``.

        Mirrors :meth:`broadcast`'s failure handling: sockets that raise
        are disconnected from the manager before iteration continues.

        Args:
            room: Name of the room whose members should receive the
                message. Unknown rooms are silently treated as empty.
            message: Text payload to deliver.
        """
        for conn in list(self._rooms.get(room, [])):
            try:
                await conn.send_text(message)
            except Exception:
                self.disconnect(conn)

    async def send_json_to_room(self, room: str, data: Any) -> None:
        """Serialize ``data`` to JSON and deliver it to every member of ``room``.

        Args:
            room: Name of the room whose members should receive the
                message.
            data: Any value accepted by ``json.dumps``.
        """
        await self.send_to_room(room, json.dumps(data))

    def join_room(self, websocket: WebSocket, room: str) -> None:
        """Add ``websocket`` to ``room`` without touching the broadcast list.

        Args:
            websocket: The connection to add. Inserted into the room
                list even when the socket is not otherwise registered
                with the manager, so callers can use rooms as a
                lightweight pub/sub on top of any pool of sockets.
            room: Name of the room to join.
        """
        self._rooms.setdefault(room, []).append(websocket)

    def leave_room(self, websocket: WebSocket, room: str) -> None:
        """Remove ``websocket`` from ``room``.

        Args:
            websocket: The connection to remove.
            room: Name of the room to leave. No error is raised when
                ``room`` is unknown or ``websocket`` is not a member.
        """
        conns = self._rooms.get(room, [])
        if websocket in conns:
            conns.remove(websocket)

    @property
    def active_connections(self) -> int:
        """Number of connections currently registered for broadcast.

        Returns:
            The length of the internal broadcast list. Connections
            that only joined a room without being broadcast members
            are not counted here.
        """
        return len(self._connections)

    def rooms(self) -> list[str]:
        """Return the names of all rooms that currently have at least one member.

        Returns:
            A new ``list`` of room name strings. Mutating the returned
            list does not affect the manager state.
        """
        return list(self._rooms.keys())
