"""
Room lifecycle management for WebRTC conferences.

``RoomManager`` — full room CRUD with auth tokens, passwords,
scheduling, and participant limits.

Usage::

    mgr = RoomManager()

    # Create a room
    room = await mgr.create_room(
        name="standup",
        password="secret",
        max_participants=10,
        scheduled_at=datetime(2026, 7, 1, 9, 0),
        duration_minutes=30,
    )

    # Auth
    token = mgr.generate_token(room.id, "alice")

    # Join validation
    room, peer_id = mgr.validate_join(room.id, token)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from rivex_adapter.webrtc.core import logger
from rivex_adapter.webrtc.conference import ConferenceBridge


@dataclass
class Room:
    """A conference room."""

    id: str
    name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    password_hash: str = ""
    max_participants: int = 0
    scheduled_at: datetime | None = None
    duration_minutes: float = 0.0
    closed: bool = False
    metadata: dict = field(default_factory=dict)
    bridge: ConferenceBridge | None = None


@dataclass
class RoomToken:
    """An authentication token for a room."""

    room_id: str
    peer_id: str
    secret: str
    expires_at: float = 0.0
    role: str = "participant"

    def is_expired(self) -> bool:
        return 0 < self.expires_at < time.time()


class RoomManager:
    """Manages room lifecycle, auth tokens, and scheduling.

    Usage::

        mgr = RoomManager(secret_key="my-secret")

        room = await mgr.create_room("standup")
        token = mgr.generate_token(room.id, "alice")
        room, peer_id = mgr.validate_join(room.id, token)
    """

    def __init__(self, secret_key: str | None = None, default_config: Any = None):
        self._secret_key = secret_key or secrets.token_hex(32)
        self._default_config = default_config
        self._rooms: dict[str, Room] = {}
        self._tokens: dict[str, list[RoomToken]] = {}
        self._on_create: list[callable] = []
        self._on_close: list[callable] = []
        self._logger = logger.getChild("room_manager")

    def on_create(self, callback: callable) -> None:
        self._on_create.append(callback)

    def on_close(self, callback: callable) -> None:
        self._on_close.append(callback)

    async def create_room(
        self,
        name: str,
        password: str = "",
        max_participants: int = 0,
        scheduled_at: datetime | None = None,
        duration_minutes: float = 0.0,
        metadata: dict | None = None,
        bridge: ConferenceBridge | None = None,
    ) -> Room:
        room_id = uuid.uuid4().hex[:12]
        if bridge is None:
            bridge = ConferenceBridge(room=room_id)
        room = Room(
            id=room_id,
            name=name,
            password_hash=self._hash_password(password) if password else "",
            max_participants=max_participants,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            metadata=metadata or {},
            bridge=bridge,
        )
        self._rooms[room_id] = room
        self._tokens[room_id] = []

        for cb in self._on_create:
            try:
                cb(room)
            except Exception:
                self._logger.exception("on_create handler error")

        self._logger.info("Room created: %s (%s)", name, room_id)
        return room

    async def close_room(self, room_id: str) -> None:
        room = self._rooms.pop(room_id, None)
        if room is None:
            raise KeyError(f"Room {room_id} not found")
        room.closed = True
        self._tokens.pop(room_id, None)

        for cb in self._on_close:
            try:
                cb(room)
            except Exception:
                self._logger.exception("on_close handler error")

        self._logger.info("Room closed: %s", room_id)

    def get_room(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def list_rooms(self, include_closed: bool = False) -> list[Room]:
        rooms = list(self._rooms.values())
        if not include_closed:
            rooms = [r for r in rooms if not r.closed]
        return rooms

    def authenticate(self, room_id: str, password: str) -> bool:
        room = self._rooms.get(room_id)
        if room is None:
            return False
        if not room.password_hash:
            return True
        return hmac.compare_digest(
            self._hash_password(password), room.password_hash
        )

    def generate_token(
        self,
        room_id: str,
        peer_id: str,
        ttl: float = 3600.0,
        role: str = "participant",
    ) -> str:
        if room_id not in self._rooms:
            raise KeyError(f"Room {room_id} not found")
        secret = secrets.token_hex(16)
        token = RoomToken(
            room_id=room_id,
            peer_id=peer_id,
            secret=secret,
            expires_at=time.time() + ttl,
            role=role,
        )
        self._tokens[room_id].append(token)
        raw = json.dumps({
            "room_id": room_id,
            "peer_id": peer_id,
            "secret": secret,
            "exp": token.expires_at,
            "role": role,
        }, separators=(",", ":"))
        sig = hmac.new(
            self._secret_key.encode(), raw.encode(), hashlib.sha256,
        ).hexdigest()
        return f"{raw}.{sig}"

    def validate_join(self, room_id: str, token_str: str) -> tuple[Room, str]:
        raw, sig = token_str.rsplit(".", 1)
        expected = hmac.new(
            self._secret_key.encode(), raw.encode(), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise PermissionError("Invalid token signature")

        payload = json.loads(raw)
        if payload["room_id"] != room_id:
            raise PermissionError("Token does not match room")

        room = self._rooms.get(room_id)
        if room is None or room.closed:
            raise KeyError(f"Room {room_id} not found or closed")

        if room.max_participants and len(room.bridge._peers) >= room.max_participants:
            raise RuntimeError("Room is full")

        peer_id = payload["peer_id"]
        if time.time() > payload.get("exp", 0) > 0:
            raise PermissionError("Token expired")

        return room, peer_id

    def revoke_token(self, room_id: str, peer_id: str) -> None:
        tokens = self._tokens.get(room_id, [])
        self._tokens[room_id] = [
            t for t in tokens if t.peer_id != peer_id
        ]

    def revoke_all_tokens(self, room_id: str) -> None:
        self._tokens[room_id] = []

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    async def auto_close_expired(self, check_interval: float = 60.0) -> None:
        while True:
            await asyncio.sleep(check_interval)
            now = datetime.utcnow()
            for room in list(self._rooms.values()):
                if room.scheduled_at and room.duration_minutes:
                    end = room.scheduled_at + timedelta(minutes=room.duration_minutes)
                    if now > end and not room.closed:
                        await self.close_room(room.id)


__all__ = [
    "RoomManager",
    "Room",
    "RoomToken",
]
