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
        """Register *callback* as the deliver-to handler for *channel_id*.

        Args:
            channel_id: Stable identifier for the channel (typically a
                UUID assigned to a WebSocket session).
            callback: Async callable invoked with each message addressed
                to the channel.
        """
        self._channels[channel_id] = callback

    def remove_channel(self, channel_id: str) -> None:
        """Drop *channel_id* from the registry and every group it belongs to.

        Both the channel-to-callback mapping and any group membership
        records are cleaned up; subsequent :meth:`send` calls for the id
        become silent no-ops.

        Args:
            channel_id: Identifier previously passed to :meth:`add_channel`.
        """
        self._channels.pop(channel_id, None)
        for group in self._groups.values():
            group.discard(channel_id)

    def join_group(self, group: str, channel_id: str) -> None:
        """Add *channel_id* to the set of members of *group*.

        Creates the group implicitly if it does not yet exist, so the
        first membership registration is safe to perform without a
        prior :meth:`add_channel` call.

        Args:
            group: Logical group name used as the broadcast target.
            channel_id: Channel to associate with the group.
        """
        if group not in self._groups:
            self._groups[group] = set()
        self._groups[group].add(channel_id)

    def leave_group(self, group: str, channel_id: str) -> None:
        """Remove *channel_id* from *group* if it is currently a member.

        Args:
            group: Group name. Unknown group names are ignored.
            channel_id: Channel to remove; missing entries are a no-op.
        """
        if group in self._groups:
            self._groups[group].discard(channel_id)

    async def send(self, channel_id: str, message: Any) -> None:
        """Deliver *message* to the channel identified by *channel_id*.

        Looks up the registered callback and awaits it. If no callback is
        registered (because the channel was removed or never added) the
        send is silently dropped.

        Args:
            channel_id: Identifier of the channel that should receive
                the message.
            message: Arbitrary JSON-serializable payload forwarded to the
                channel's callback.
        """
        cb = self._channels.get(channel_id)
        if cb:
            await cb(message)

    async def group_send(self, group: str, message: Any) -> None:
        """Fan *message* out to every channel currently in *group*.

        Args:
            group: Group name as used in :meth:`join_group`. Sends to an
                empty or unknown group complete without errors.
            message: Payload delivered to every member channel.
        """
        channel_ids = self._groups.get(group, set())
        tasks = [self.send(cid, message) for cid in channel_ids]
        await asyncio.gather(*tasks)

    async def broadcast(self, message: Any) -> None:
        """Send *message* to every registered channel in parallel.

        Args:
            message: Payload delivered to every channel's callback.
        """
        tasks = [cb(message) for cb in self._channels.values()]
        await asyncio.gather(*tasks)

    def _redis_connected(self) -> bool:
        """Return whether a Redis client is currently attached."""
        return self._redis is not None

    async def connect_redis(self) -> None:
        """Establish the Redis pub/sub connection used by the multi-process backend.

        The method is a no-op unless the layer was constructed with
        ``backend="redis"`` and no client has been opened yet. On a
        successful connection it starts a background
        :meth:`_redis_listener` task that fans Redis messages out to
        in-process subscribers.
        """
        if self._backend_name != "redis" or self._redis:
            return
        import redis.asyncio as aioredis
        self._redis = await aioredis.from_url(self._url or "redis://localhost:6379")
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe("rivex:broadcast")
        asyncio.create_task(self._redis_listener())

    async def _redis_listener(self) -> None:
        """Forward Redis pub/sub messages to local subscribers.

        Runs as a long-lived task spawned by :meth:`connect_redis` and
        decodes each ``rivex:broadcast`` payload, dispatching to either
        :meth:`group_send` (when a group is present) or :meth:`broadcast`.
        Malformed payloads are swallowed so a single bad message cannot
        stop the listener.
        """
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
        """Publish *message* on the shared Redis channel.

        Lazily opens the Redis connection when one is not yet attached.
        The message is wrapped in a ``{"group": ..., "message": ...}``
        envelope so :meth:`_redis_listener` on every process can route it
        to the correct in-process group or fall back to a global
        broadcast.

        Args:
            group: Optional group name. ``None`` triggers a global
                broadcast on the receiving side.
            message: JSON-serializable payload to publish.
        """
        if not self._redis:
            await self.connect_redis()
        if self._redis:
            payload = json.dumps({"group": group, "message": message})
            await self._redis.publish("rivex:broadcast", payload)

    async def close(self) -> None:
        """Close the Redis client and detach it from the layer.

        The :meth:`_redis_listener` task is left to terminate on its own
        once the underlying pubsub object stops yielding messages.
        """
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
        """Send *message* over the underlying WebSocket connection.

        Dict and list payloads are JSON-encoded before being written. If
        the channel has been closed or the send raises, the channel is
        marked closed so subsequent calls short-circuit.

        Args:
            message: Either a string/bytes payload or a JSON-serializable
                structure to forward to the client.
        """
        if self._closed:
            return
        try:
            if isinstance(message, (dict, list)):
                message = json.dumps(message)
            await self._ws.send(message)
        except Exception:
            self._closed = True

    async def receive(self) -> Any:
        """Read the next message from the WebSocket.

        Returns:
            The decoded message as a string for text frames, ``bytes`` for
            binary frames, or ``None`` if the channel was closed mid-read.
        """
        try:
            data = await self._ws.receive()
            if isinstance(data, (bytes, bytearray)):
                return data.decode()
            return data
        except Exception:
            self._closed = True
            return None

    async def listen(self, on_message: Callable | None = None) -> None:
        """Loop receiving messages and dispatching them to *on_message*.

        Each iteration calls :meth:`receive`; if the channel is closed
        the loop exits cleanly. The optional *on_message* callback is
        awaited with the channel and the decoded message.

        Args:
            on_message: Optional async callable invoked as
                ``on_message(channel, message)`` for every received
                message. When ``None`` the messages are simply consumed.
        """
        while not self._closed:
            msg = await self.receive()
            if msg is None:
                break
            if on_message:
                await on_message(self, msg)

    async def close(self) -> None:
        """Mark the channel closed and close the underlying WebSocket.

        Errors raised while closing the transport are swallowed so the
        caller can still rely on the channel being marked as closed.
        """
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
        """Create or fetch a :class:`Room` handle for *name*.

        Rooms are created lazily and cached, so calling ``new_room`` for
        an existing name is safe and idempotent.

        Args:
            name: Logical room name used as a broadcast target.

        Returns:
            A :class:`Room` bound to this broadcast instance.
        """
        if name not in self._rooms:
            self._rooms[name] = set()
        return Room(name, self)

    def delete_room(self, name: str) -> None:
        """Remove *name* from the room registry.

        Args:
            name: Room name to drop. Unknown rooms are silently ignored.
        """
        self._rooms.pop(name, None)

    def join(self, room: str, channel_id: str, user_id: str | None = None) -> None:
        """Add *channel_id* to *room* and optionally index it under *user_id*.

        Args:
            room: Room name to join. Created if missing.
            channel_id: Identifier of the channel joining the room.
            user_id: Optional user identifier; when supplied the channel
                is also recorded under this user for :meth:`to_user`.
        """
        if room not in self._rooms:
            self._rooms[room] = set()
        self._rooms[room].add(channel_id)
        if user_id:
            if user_id not in self._user_channels:
                self._user_channels[user_id] = set()
            self._user_channels[user_id].add(channel_id)
        self._layer.join_group(f"room:{room}", channel_id)

    def leave(self, room: str, channel_id: str, user_id: str | None = None) -> None:
        """Remove *channel_id* from *room* and (if given) the user index.

        Args:
            room: Room name. Unknown rooms are ignored.
            channel_id: Identifier of the channel leaving.
            user_id: Optional user identifier whose index should be
                cleaned up alongside the room membership.
        """
        if room in self._rooms:
            self._rooms[room].discard(channel_id)
        if user_id:
            self._user_channels.get(user_id, set()).discard(channel_id)
        self._layer.leave_group(f"room:{room}", channel_id)

    async def broadcast(self, room: str, message: Any) -> None:
        """Send *message* to every channel currently in *room*."""
        await self._layer.group_send(f"room:{room}", message)

    async def broadcast_all(self, message: Any) -> None:
        """Send *message* to every channel on the underlying layer."""
        await self._layer.broadcast(message)

    async def to_user(self, user_id: str, message: Any) -> None:
        """Deliver *message* to all channels registered for *user_id*.

        Channels are looked up in the user index populated by
        :meth:`join`; if the user has no associated channels the call
        completes without errors.
        """
        channels = self._user_channels.get(user_id, set())
        for cid in channels:
            await self._layer.send(cid, message)

    def room_members(self, room: str) -> int:
        """Return the number of channels currently joined to *room*."""
        return len(self._rooms.get(room, set()))

    def active_rooms(self) -> list[str]:
        """Return the list of room names that currently have at least one member."""
        return [name for name, members in self._rooms.items() if members]


class Room:
    """Represents a named room for broadcasting."""

    def __init__(self, name: str, broadcast: WebSocketBroadcast):
        self.name = name
        self._broadcast = broadcast

    async def broadcast(self, message: Any) -> None:
        """Send *message* to every channel currently in this room."""
        await self._broadcast.broadcast(self.name, message)

    def member_count(self) -> int:
        """Return the number of channels currently joined to this room."""
        return self._broadcast.room_members(self.name)

    def join(self, channel_id: str, user_id: str | None = None) -> None:
        """Join *channel_id* to this room, optionally indexing under *user_id*."""
        self._broadcast.join(self.name, channel_id, user_id)

    def leave(self, channel_id: str, user_id: str | None = None) -> None:
        """Remove *channel_id* from this room, optionally cleaning the user index."""
        self._broadcast.leave(self.name, channel_id, user_id)
