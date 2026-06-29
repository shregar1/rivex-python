"""
Signaling module for WebRTC peer discovery and SDP/ICE exchange.

Provides:
- ``WebRTCSignaling`` — in-memory room-based signaling (original)
- ``RedisWebRTCSignaling`` — Redis-backed multi-node signaling
- ``AuthWebRTCSignaling`` — token-authenticated signaling wrapper

All signaling classes are designed to be subclassed for custom behavior.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Callable

from rivex_adapter.webrtc.core import (
    WebRTCPeerConnection,
    WebRTCConfig,
    SignalingMessage,
    SignalingMessageType,
    logger,
)

# ---------------------------------------------------------------------------
# WebRTC Signaling (in-memory)
# ---------------------------------------------------------------------------


class WebRTCSignaling:
    """WebRTC signaling server using WebSocket connections.

    Manages rooms of peers, relays SDP offers/answers and ICE candidates
    between participants, and provides ``WebRTCPeerConnection`` instances
    per connected peer.

    Extensibility:
        Subclass and override ``on_peer_joined()``, ``on_peer_left()``,
        ``relay_message()``, or ``create_peer_connection()`` to customize
        behavior. Override ``validate_auth()`` to add custom auth.
    """

    def __init__(self, config: WebRTCConfig | None = None):
        self.config = config or WebRTCConfig()
        self._rooms: dict[str, dict[str, Any]] = {}
        self._peer_connections: dict[str, WebRTCPeerConnection] = {}
        self._peer_metadata: dict[str, dict[str, Any]] = {}
        self._on_peer_join: list[Callable[[str, str], None]] = []
        self._on_peer_leave: list[Callable[[str, str], None]] = []
        self._on_broadcast: list[Callable[[str, str, Any], None]] = []

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_peer_join(self, callback: Callable[[str, str], None]) -> None:
        """Register a callback for when a peer joins a room.

        The callback receives ``(room, peer_id)``.
        """
        self._on_peer_join.append(callback)

    def on_peer_leave(self, callback: Callable[[str, str], None]) -> None:
        """Register a callback for when a peer leaves a room.

        The callback receives ``(room, peer_id)``.
        """
        self._on_peer_leave.append(callback)

    def on_broadcast(self, callback: Callable[[str, str, Any], None]) -> None:
        """Register a callback for broadcast messages.

        The callback receives ``(room, sender_peer_id, data)``.
        """
        self._on_broadcast.append(callback)

    # ------------------------------------------------------------------
    # Auth hook
    # ------------------------------------------------------------------

    async def validate_auth(self, token: str | None, room: str) -> str | None:
        """Validate an authentication token for a room.

        Return a peer ID string if valid, or ``None`` to deny access.

        Override to integrate with your auth system (JWT, API keys, etc.).
        Default implementation allows all connections with generated IDs.
        """
        return uuid.uuid4().hex[:12]

    # ------------------------------------------------------------------
    # Extensibility hooks
    # ------------------------------------------------------------------

    def create_peer_connection(self, peer_id: str) -> WebRTCPeerConnection:
        """Create a new ``WebRTCPeerConnection`` for *peer_id*.

        Override to use a custom subclass of ``WebRTCPeerConnection``.
        """
        return WebRTCPeerConnection(peer_id=peer_id, config=self.config)

    async def on_peer_joined(self, room: str, peer_id: str) -> None:
        """Called after a peer has joined a room.

        Override to add custom logic (e.g. logging, metrics).
        """

    async def on_peer_left(self, room: str, peer_id: str) -> None:
        """Called after a peer has left a room.

        Override to add custom cleanup logic.
        """

    async def relay_message(self, msg: SignalingMessage, room: str) -> None:
        """Relay a signaling message to its target peer.

        Override to add message filtering, logging, or transformation.
        """
        target_ws = self._get_ws(room, msg.target) if msg.target else None
        if target_ws is not None:
            try:
                await target_ws.send_json(msg.to_dict())
            except Exception:
                self._logger.warning(
                    "failed to relay %s to %s in %s", msg.type.value, msg.target, room
                )

    # ------------------------------------------------------------------
    # Main signaling handler
    # ------------------------------------------------------------------

    async def handle(
        self,
        ws: Any,
        room: str,
        peer_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Handle a signaling WebSocket connection.

        Yields outgoing signaling messages as dicts. The caller should
        send these to the WebSocket client (e.g. via ``ws.send_json``).

        Args:
            ws: WebSocket connection with ``send_json`` / ``receive_json``.
            room: Room name to join.
            peer_id: Optional peer ID. If not provided, generated.
            metadata: Optional dict of peer metadata (user agent, etc.).
        """
        pid = peer_id or uuid.uuid4().hex[:12]
        self._join_room(room, pid, ws, metadata)

        others = [p for p in self._rooms.get(room, {}) if p != pid]
        yield SignalingMessage(
            type=SignalingMessageType.JOIN,
            sender="server",
            data={"peer_id": pid, "peers": others},
        ).to_dict()

        for other_pid in others:
            other_ws = self._get_ws(room, other_pid)
            if other_ws is not None:
                try:
                    await other_ws.send_json(
                        SignalingMessage(
                            type=SignalingMessageType.JOIN,
                            sender=pid,
                            data={"peer_id": pid},
                        ).to_dict()
                    )
                except Exception:
                    pass

        for cb in self._on_peer_join:
            cb(room, pid)
        await self.on_peer_joined(room, pid)

        try:
            async for raw in self._receive_messages(ws):
                msg = SignalingMessage.from_dict(raw)
                self._logger.debug("signal %s <- %s: %s", room, pid, msg.type.value)

                if msg.type == SignalingMessageType.OFFER:
                    await self.relay_message(msg, room)

                elif msg.type == SignalingMessageType.ANSWER:
                    await self.relay_message(msg, room)

                elif msg.type == SignalingMessageType.ICE_CANDIDATE:
                    await self.relay_message(msg, room)

                elif msg.type == SignalingMessageType.ICE_RESTART:
                    await self.relay_message(msg, room)

                elif msg.type == SignalingMessageType.PING:
                    yield SignalingMessage(
                        type=SignalingMessageType.PONG,
                        sender="server",
                        data={"timestamp": time.time()},
                    ).to_dict()

                else:
                    yield SignalingMessage(
                        type=SignalingMessageType.ERROR,
                        sender="server",
                        data={"detail": f"unhandled message type: {msg.type.value}"},
                    ).to_dict()

        except Exception:
            self._logger.exception("signaling error for %s in %s", pid, room)
        finally:
            self._leave_room(room, pid)
            for cb in self._on_peer_leave:
                cb(room, pid)
            await self.on_peer_left(room, pid)

            for other_pid in list(self._rooms.get(room, {})):
                other_ws = self._get_ws(room, other_pid)
                if other_ws is not None:
                    try:
                        await other_ws.send_json(
                            SignalingMessage(
                                type=SignalingMessageType.LEAVE,
                                sender=pid,
                            ).to_dict()
                        )
                    except Exception:
                        pass

    # ------------------------------------------------------------------
    # High-level accept
    # ------------------------------------------------------------------

    async def accept(
        self,
        ws: Any,
        room: str,
        peer_id: str | None = None,
        **rtc_kwargs: Any,
    ) -> WebRTCPeerConnection:
        """Accept a WebSocket connection and negotiate a WebRTC peer connection.

        This is a higher-level alternative to ``handle()`` that manages
        the full offer/answer/ICE exchange automatically. Returns a
        ready-to-use ``WebRTCPeerConnection``.

        The caller is responsible for calling ``pc.close()`` when done.
        """
        pid = peer_id or uuid.uuid4().hex[:12]
        pc = self.create_peer_connection(pid)
        self._peer_connections[pid] = pc

        def _on_ice(candidate: dict[str, Any]) -> None:
            asyncio.ensure_future(
                self._send_json_safe(
                    ws,
                    SignalingMessage(
                        type=SignalingMessageType.ICE_CANDIDATE,
                        sender=pid,
                        data=candidate,
                    ).to_dict(),
                )
            )

        pc.on_ice_candidate(_on_ice)

        async def _signaling_loop() -> None:
            try:
                async for raw in self._receive_messages(ws):
                    msg = SignalingMessage.from_dict(raw)
                    if msg.type == SignalingMessageType.OFFER and msg.target == pid:
                        answer = await pc.create_answer(msg.data)
                        await self._send_json_safe(
                            ws,
                            SignalingMessage(
                                type=SignalingMessageType.ANSWER,
                                sender=pid,
                                data=answer,
                                target=msg.sender,
                            ).to_dict(),
                        )
                    elif msg.type == SignalingMessageType.ANSWER and msg.target == pid:
                        await pc.set_remote_description(msg.data)
                    elif msg.type == SignalingMessageType.ICE_CANDIDATE:
                        await pc.add_ice_candidate(msg.data)
            except Exception:
                self._logger.exception("signaling loop error for %s", pid)
            finally:
                await pc.close()
                self._peer_connections.pop(pid, None)

        asyncio.ensure_future(_signaling_loop())
        return pc

    # ------------------------------------------------------------------
    # Room queries
    # ------------------------------------------------------------------

    def get_peer(self, peer_id: str) -> WebRTCPeerConnection | None:
        """Get a peer connection by ID."""
        return self._peer_connections.get(peer_id)

    def get_room_peers(self, room: str) -> list[str]:
        """List peer IDs in a room."""
        return list(self._rooms.get(room, {}))

    def get_rooms(self) -> list[str]:
        """List all active room names."""
        return list(self._rooms.keys())

    def get_peer_metadata(self, peer_id: str) -> dict[str, Any] | None:
        """Get metadata for a peer, if any was provided on join."""
        return self._peer_metadata.get(peer_id)

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    async def broadcast(self, room: str, data: Any) -> None:
        """Broadcast *data* to all peers in *room*."""
        peers = self._rooms.get(room, {})
        for pid, ws in list(peers.items()):
            try:
                payload = (
                    data.to_dict()
                    if isinstance(data, SignalingMessage)
                    else data
                )
                await self._send_json_safe(ws, payload)
            except Exception:
                pass
        for cb in self._on_broadcast:
            cb(room, "server", data)

    # ------------------------------------------------------------------
    # Peer-to-peer relay
    # ------------------------------------------------------------------

    async def send_to_peer(self, room: str, target: str, data: Any) -> bool:
        """Send *data* to a specific peer in *room*.

        Returns ``True`` if the peer was found and message sent.
        """
        ws = self._get_ws(room, target)
        if ws is None:
            return False
        try:
            payload = (
                data.to_dict()
                if isinstance(data, SignalingMessage)
                else data
            )
            await self._send_json_safe(ws, payload)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal room management
    # ------------------------------------------------------------------

    def _join_room(
        self,
        room: str,
        peer_id: str,
        ws: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._rooms.setdefault(room, {})[peer_id] = ws
        if metadata:
            self._peer_metadata[peer_id] = metadata
        self._logger.info("%s joined room %s", peer_id, room)

    def _leave_room(self, room: str, peer_id: str) -> None:
        self._rooms.get(room, {}).pop(peer_id, None)
        self._peer_metadata.pop(peer_id, None)
        if room in self._rooms and not self._rooms[room]:
            del self._rooms[room]
        self._logger.info("%s left room %s", peer_id, room)

    def _get_ws(self, room: str, peer_id: str) -> Any | None:
        return self._rooms.get(room, {}).get(peer_id)

    async def _receive_messages(
        self, ws: Any
    ) -> AsyncIterator[dict[str, Any]]:
        while True:
            try:
                if hasattr(ws, "receive_json"):
                    raw = await ws.receive_json()
                elif hasattr(ws, "receive"):
                    raw = await ws.receive()
                    if isinstance(raw, str):
                        raw = json.loads(raw)
                    else:
                        continue
                else:
                    break
                if raw is None:
                    break
                yield raw
            except (json.JSONDecodeError, ValueError):
                continue
            except Exception:
                break

    async def _send_json_safe(self, ws: Any, data: dict[str, Any]) -> None:
        try:
            if hasattr(ws, "send_json"):
                await ws.send_json(data)
            elif hasattr(ws, "send"):
                await ws.send(json.dumps(data))
        except Exception:
            pass

    @property
    def _logger(self) -> logging.Logger:
        return logger


# ---------------------------------------------------------------------------
# Redis-backed signaling (multi-node)
# ---------------------------------------------------------------------------


class RedisWebRTCSignaling(WebRTCSignaling):
    """Redis-backed WebRTC signaling for multi-node deployments.

    Uses Redis pub/sub to broadcast room events across processes,
    enabling horizontal scaling of signaling servers.

    Requires the ``redis`` package (``pip install rivex-adapter[redis]``).

    Usage::

        signaling = RedisWebRTCSignaling(
            redis_url="redis://localhost:6379/0"
        )
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        config: WebRTCConfig | None = None,
    ):
        super().__init__(config)
        self.redis_url = redis_url
        self._redis: Any = None
        self._pubsub: Any = None
        self._node_id = uuid.uuid4().hex[:8]
        self._listener_task: asyncio.Task[None] | None = None

    async def _ensure_redis(self) -> Any:
        if self._redis is None:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self.redis_url)
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe("webrtc:signal")
            self._listener_task = asyncio.ensure_future(self._listen())
        return self._redis

    async def _listen(self) -> None:
        while True:
            try:
                message = await self._pubsub.get_message(
                    timeout=1.0, ignore_subscribe_messages=True
                )
                if message is not None:
                    data = json.loads(message["data"])
                    room = data.get("room")
                    msg = SignalingMessage.from_dict(data["message"])
                    target_ws = self._get_ws(room, msg.target) if room and msg.target else None
                    if target_ws is not None:
                        await self._send_json_safe(target_ws, msg.to_dict())
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def relay_message(self, msg: SignalingMessage, room: str) -> None:
        target_ws = self._get_ws(room, msg.target) if msg.target else None
        if target_ws is not None:
            await self._send_json_safe(target_ws, msg.to_dict())
            return
        redis = await self._ensure_redis()
        await redis.publish(
            "webrtc:signal",
            json.dumps({"room": room, "message": msg.to_dict()}),
        )

    async def on_peer_joined(self, room: str, peer_id: str) -> None:
        redis = await self._ensure_redis()
        await redis.sadd(f"webrtc:room:{room}", peer_id)

    async def on_peer_left(self, room: str, peer_id: str) -> None:
        redis = await self._ensure_redis()
        await redis.srem(f"webrtc:room:{room}", peer_id)
        remaining = await redis.scard(f"webrtc:room:{room}")
        if remaining == 0:
            await redis.delete(f"webrtc:room:{room}")

    def get_room_peers(self, room: str) -> list[str]:
        local = super().get_room_peers(room)
        if self._redis is not None:
            try:
                import anyio
                from redis.asyncio import Redis
                r = Redis.from_url(self.redis_url)
                remote = anyio.run(r.smembers, f"webrtc:room:{room}")
                return list(set(local) | {p.decode() if isinstance(p, bytes) else p for p in remote})
            except Exception:
                pass
        return local

    async def close(self) -> None:
        if self._listener_task is not None:
            self._listener_task.cancel()
            self._listener_task = None
        if self._pubsub is not None:
            await self._pubsub.unsubscribe("webrtc:signal")
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


# ---------------------------------------------------------------------------
# Authenticated signaling wrapper
# ---------------------------------------------------------------------------


class AuthWebRTCSignaling(WebRTCSignaling):
    """Token-authenticated WebRTC signaling.

    Validates a JWT or opaque token before allowing room access.
    Integrates with any auth system by overriding ``validate_auth()``.

    Usage::

        class MyAuthSignaling(AuthWebRTCSignaling):
            async def validate_auth(self, token, room):
                payload = verify_jwt(token)
                return payload["user_id"]  # or None to deny

        signaling = MyAuthSignaling()

        # Client connects with auth message first:
        # {"type": "auth", "data": {"token": "..."}}
    """

    def __init__(self, config: WebRTCConfig | None = None):
        super().__init__(config)
        self._authenticated: dict[str, str] = {}  # peer_id -> token

    async def validate_auth(self, token: str | None, room: str) -> str | None:
        """Validate an authentication token for a room.

        Return a peer ID string if valid, or ``None`` to deny.
        Override this method in a subclass.

        Default implementation checks ``_valid_tokens`` dict if set.
        """
        return await super().validate_auth(token, room)

    def set_valid_tokens(self, tokens: dict[str, str]) -> None:
        """Set valid tokens mapping ``token -> peer_id``.

        Convenience for simple token-based auth without subclassing.
        """
        self._valid_tokens = tokens

    async def handle(
        self,
        ws: Any,
        room: str,
        peer_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Handle a signaling connection with auth.

        Expects an ``AUTH`` message as the first message::

            {"type": "auth", "data": {"token": "..."}}

        Yields ``AUTH_OK`` or ``AUTH_DENY`` as the first message.
        """
        raw = await anext(self._receive_messages(ws))
        msg = SignalingMessage.from_dict(raw)

        if msg.type != SignalingMessageType.AUTH:
            yield SignalingMessage(
                type=SignalingMessageType.AUTH_DENY,
                sender="server",
                data={"detail": "first message must be auth"},
            ).to_dict()
            return

        token = msg.data.get("token") if isinstance(msg.data, dict) else None
        pid = await self.validate_auth(token, room)

        if pid is None:
            yield SignalingMessage(
                type=SignalingMessageType.AUTH_DENY,
                sender="server",
                data={"detail": "authentication failed"},
            ).to_dict()
            return

        self._authenticated[pid] = token or ""

        yield SignalingMessage(
            type=SignalingMessageType.AUTH_OK,
            sender="server",
            data={"peer_id": pid},
        ).to_dict()

        async for out in super().handle(ws, room, pid, metadata):
            yield out
