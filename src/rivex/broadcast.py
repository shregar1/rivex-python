from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from typing import Any


class ChannelLayer:
    """Pub/sub channel layer for WebSocket broadcast.

    Supports in-memory (single process) and Redis (multi-process) backends.
    """

    def __init__(self, backend: str = "memory", url: str | None = None):
        self._backend_name = backend
        self._url = url
        self._groups: dict[str, set[str]] = {}
        self._channels: dict[str, Callable] = {}

        if backend == "redis":
            self._redis = None
            self._pubsub = None

    def add_channel(self, channel_id: str, callback: Callable) -> None:
        self._channels[channel_id] = callback

    def remove_channel(self, channel_id: str) -> None:
        self._channels.pop(channel_id, None)
        for group in self._groups.values():
            group.discard(channel_id)

    def join_group(self, group: str, channel_id: str) -> None:
        if group not in self._groups:
            self._groups[group] = set()
        self._groups[group].add(channel_id)

    def leave_group(self, group: str, channel_id: str) -> None:
        if group in self._groups:
            self._groups[group].discard(channel_id)

    async def send(self, channel_id: str, message: Any) -> None:
        cb = self._channels.get(channel_id)
        if cb:
            await cb(message)

    async def group_send(self, group: str, message: Any) -> None:
        channel_ids = self._groups.get(group, set())
        tasks = [self.send(cid, message) for cid in channel_ids]
        await asyncio.gather(*tasks)

    async def broadcast(self, message: Any) -> None:
        tasks = [cb(message) for cb in self._channels.values()]
        await asyncio.gather(*tasks)

    def _redis_connected(self) -> bool:
        return self._redis is not None

    async def connect_redis(self) -> None:
        if self._backend_name != "redis" or self._redis:
            return
        import redis.asyncio as aioredis
        self._redis = await aioredis.from_url(self._url or "redis://localhost:6379")
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe("rivex:broadcast")
        asyncio.create_task(self._redis_listener())

    async def _redis_listener(self) -> None:
        if not self._pubsub:
            return
        async for msg in self._pubsub.listen():
            if msg["type"] == "message":
                try:
                    data = json.loads(msg["data"])
                    group = data.get("group")
                    message = data.get("message")
                    if group:
                        await self.group_send(group, message)
                    else:
                        await self.broadcast(message)
                except Exception:
                    pass

    async def redis_publish(self, group: str | None, message: Any) -> None:
        if not self._redis:
            await self.connect_redis()
        if self._redis:
            payload = json.dumps({"group": group, "message": message})
            await self._redis.publish("rivex:broadcast", payload)

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None


class WebSocketChannel:
    """Wraps a WebSocket connection for use with ChannelLayer.

    Usage::

        @app.websocket("/ws")
        async def ws(websocket):
            channel = WebSocketChannel(websocket)
            channel_layer.add_channel(channel.id, channel.send)
            await channel.listen()
    """

    def __init__(self, websocket: Any, auto_ping_interval: float = 30.0):
        self._ws = websocket
        self._auto_ping = auto_ping_interval
        self.id = str(uuid.uuid4())
        self._closed = False

    async def send(self, message: Any) -> None:
        if self._closed:
            return
        try:
            if isinstance(message, (dict, list)):
                message = json.dumps(message)
            await self._ws.send(message)
        except Exception:
            self._closed = True

    async def receive(self) -> Any:
        try:
            data = await self._ws.receive()
            if isinstance(data, (bytes, bytearray)):
                return data.decode()
            return data
        except Exception:
            self._closed = True
            return None

    async def listen(self, on_message: Callable | None = None) -> None:
        while not self._closed:
            msg = await self.receive()
            if msg is None:
                break
            if on_message:
                await on_message(self, msg)

    async def close(self) -> None:
        self._closed = True
        try:
            await self._ws.close()
        except Exception:
            pass


class WebSocketBroadcast:
    """High-level broadcast API for WebSocket rooms.

    Usage::

        broadcast = WebSocketBroadcast(channel_layer)
        room = broadcast.new_room("lobby")
        room.broadcast("Hello everyone!")
        broadcast.to_user("user_123", "Private message")
    """

    def __init__(self, channel_layer: ChannelLayer):
        self._layer = channel_layer
        self._rooms: dict[str, set[str]] = {}
        self._user_channels: dict[str, set[str]] = {}

    def new_room(self, name: str) -> Room:
        if name not in self._rooms:
            self._rooms[name] = set()
        return Room(name, self)

    def delete_room(self, name: str) -> None:
        self._rooms.pop(name, None)

    def join(self, room: str, channel_id: str, user_id: str | None = None) -> None:
        if room not in self._rooms:
            self._rooms[room] = set()
        self._rooms[room].add(channel_id)
        if user_id:
            if user_id not in self._user_channels:
                self._user_channels[user_id] = set()
            self._user_channels[user_id].add(channel_id)
        self._layer.join_group(f"room:{room}", channel_id)

    def leave(self, room: str, channel_id: str, user_id: str | None = None) -> None:
        if room in self._rooms:
            self._rooms[room].discard(channel_id)
        if user_id:
            self._user_channels.get(user_id, set()).discard(channel_id)
        self._layer.leave_group(f"room:{room}", channel_id)

    async def broadcast(self, room: str, message: Any) -> None:
        await self._layer.group_send(f"room:{room}", message)

    async def broadcast_all(self, message: Any) -> None:
        await self._layer.broadcast(message)

    async def to_user(self, user_id: str, message: Any) -> None:
        channels = self._user_channels.get(user_id, set())
        for cid in channels:
            await self._layer.send(cid, message)

    def room_members(self, room: str) -> int:
        return len(self._rooms.get(room, set()))

    def active_rooms(self) -> list[str]:
        return [name for name, members in self._rooms.items() if members]


class Room:
    """Represents a named room for broadcasting."""

    def __init__(self, name: str, broadcast: WebSocketBroadcast):
        self.name = name
        self._broadcast = broadcast

    async def broadcast(self, message: Any) -> None:
        await self._broadcast.broadcast(self.name, message)

    def member_count(self) -> int:
        return self._broadcast.room_members(self.name)

    def join(self, channel_id: str, user_id: str | None = None) -> None:
        self._broadcast.join(self.name, channel_id, user_id)

    def leave(self, channel_id: str, user_id: str | None = None) -> None:
        self._broadcast.leave(self.name, channel_id, user_id)
