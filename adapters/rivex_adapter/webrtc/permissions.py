"""
Room and peer permission system for WebRTC conferences.

Provides:

- ``Permission`` — granular permission enumerations
- ``Role`` — a preset collection of permissions
- ``PeerPermissions`` — per-peer permission assignments
- ``PermissionMiddleware`` — FastAPI/Rivex middleware that enforces
  permissions on ``on_join`` / ``on_leave``

Usage::

    perms = PeerPermissions()

    # Define roles
    host = Role("host", permissions=[
        Permission.MUTE_PEER,
        Permission.KICK_PEER,
        Permission.RECORD,
        Permission.SHARE_SCREEN,
        Permission.CHAT,
    ])
    perms.define_role("host", host)

    # Assign
    perms.set_role("alice", "host")

    # Check
    if perms.can("bob", Permission.SHARE_SCREEN):
        ...
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any


class Permission(str, enum.Enum):
    """Granular permissions within a conference."""

    # --- Audio ---
    MUTE_SELF = "audio.mute_self"
    MUTE_OTHERS = "audio.mute_others"
    MUTE_ALL = "audio.mute_all"
    AUDIO_QUALITY = "audio.quality"  # choose bitrate/codec

    # --- Video ---
    ENABLE_VIDEO = "video.enable"
    DISABLE_OTHERS_VIDEO = "video.disable_others"
    VIDEO_QUALITY = "video.quality"

    # --- Screen share ---
    SHARE_SCREEN = "screen.share"
    VIEW_SCREEN = "screen.view"
    CONTROL_REMOTE = "screen.control_remote"

    # --- Chat ---
    CHAT = "chat.send"
    READ_CHAT = "chat.read"
    DELETE_MESSAGE = "chat.delete_message"
    CLEAR_CHAT = "chat.clear"

    # --- Recording ---
    RECORD = "recording.start"
    STOP_RECORDING = "recording.stop"
    ACCESS_RECORDINGS = "recording.access"

    # --- Moderation ---
    KICK_PEER = "moderation.kick"
    BAN_PEER = "moderation.ban"
    LOCK_ROOM = "moderation.lock_room"
    PROMOTE = "moderation.promote"
    MUTE_ALL_VIDEO = "moderation.mute_all_video"

    # --- Room ---
    CREATE_ROOM = "room.create"
    DELETE_ROOM = "room.delete"
    LIST_PEERS = "room.list_peers"
    CHANGE_TOPIC = "room.change_topic"
    SET_PASSWORD = "room.set_password"

    # --- Data ---
    SEND_DATA = "data.send"
    RECEIVE_DATA = "data.receive"

    # --- Admin ---
    ALL = "admin.all"  # super-admin bypass


class PermissionSet(set):
    """A set of :class:`Permission` values with utility methods."""

    def grants(self, permission: Permission) -> bool:
        """Check if this set grants the given permission.

        The ``ALL`` wildcard always returns ``True``.
        """
        return Permission.ALL in self or permission in self

    def grants_any(self, *permissions: Permission) -> bool:
        return any(self.grants(p) for p in permissions)

    def grants_all(self, *permissions: Permission) -> bool:
        return all(self.grants(p) for p in permissions)

    @classmethod
    def all_permissions(cls) -> PermissionSet:
        """Return a set of every defined permission."""
        return cls(p.value for p in Permission)


@dataclass
class Role:
    """A named role with a fixed set of permissions."""

    name: str
    permissions: list[Permission]
    description: str = ""
    priority: int = 0  # higher = more authority

    def to_set(self) -> PermissionSet:
        return PermissionSet(self.permissions)

    def grants(self, permission: Permission) -> bool:
        return self.to_set().grants(permission)


# ---- Built-in roles -------------------------------------------------------


ROLE_ADMIN = Role(
    name="admin",
    permissions=list(Permission),
    description="Full access to everything",
    priority=100,
)

ROLE_MODERATOR = Role(
    name="moderator",
    permissions=[
        Permission.MUTE_SELF,
        Permission.MUTE_OTHERS,
        Permission.MUTE_ALL,
        Permission.DISABLE_OTHERS_VIDEO,
        Permission.KICK_PEER,
        Permission.BAN_PEER,
        Permission.LOCK_ROOM,
        Permission.MUTE_ALL_VIDEO,
        Permission.CHAT,
        Permission.READ_CHAT,
        Permission.DELETE_MESSAGE,
        Permission.CLEAR_CHAT,
        Permission.SHARE_SCREEN,
        Permission.VIEW_SCREEN,
        Permission.RECORD,
        Permission.STOP_RECORDING,
        Permission.ACCESS_RECORDINGS,
        Permission.SEND_DATA,
        Permission.RECEIVE_DATA,
        Permission.LIST_PEERS,
        Permission.CHANGE_TOPIC,
        Permission.ENABLE_VIDEO,
        Permission.VIDEO_QUALITY,
        Permission.AUDIO_QUALITY,
    ],
    description="Can moderate all peers",
    priority=80,
)

ROLE_PRESENTER = Role(
    name="presenter",
    permissions=[
        Permission.MUTE_SELF,
        Permission.ENABLE_VIDEO,
        Permission.AUDIO_QUALITY,
        Permission.VIDEO_QUALITY,
        Permission.SHARE_SCREEN,
        Permission.VIEW_SCREEN,
        Permission.CHAT,
        Permission.READ_CHAT,
        Permission.SEND_DATA,
        Permission.RECEIVE_DATA,
        Permission.LIST_PEERS,
    ],
    description="Can share screen and present",
    priority=50,
)

ROLE_PARTICIPANT = Role(
    name="participant",
    permissions=[
        Permission.MUTE_SELF,
        Permission.ENABLE_VIDEO,
        Permission.CHAT,
        Permission.READ_CHAT,
        Permission.VIEW_SCREEN,
        Permission.SEND_DATA,
        Permission.RECEIVE_DATA,
        Permission.LIST_PEERS,
    ],
    description="Standard conference participant",
    priority=10,
)

ROLE_LISTENER = Role(
    name="listener",
    permissions=[
        Permission.VIEW_SCREEN,
        Permission.READ_CHAT,
        Permission.RECEIVE_DATA,
        Permission.LIST_PEERS,
    ],
    description="Read-only listener",
    priority=0,
)

BUILTIN_ROLES: dict[str, Role] = {
    "admin": ROLE_ADMIN,
    "moderator": ROLE_MODERATOR,
    "presenter": ROLE_PRESENTER,
    "participant": ROLE_PARTICIPANT,
    "listener": ROLE_LISTENER,
}


# ---- Peer Permissions Store ------------------------------------------------


@dataclass
class PeerPermissionEntry:
    """Permissions for a single peer."""

    peer_id: str
    role: str = "participant"
    custom_permissions: PermissionSet = field(default_factory=PermissionSet)
    denied_permissions: PermissionSet = field(default_factory=PermissionSet)
    is_owner: bool = False

    def effective_permissions(self) -> PermissionSet:
        """Compute effective permission set (role + custom - denied)."""
        role = BUILTIN_ROLES.get(self.role)
        if self.is_owner:
            return PermissionSet.all_permissions()
        perms = PermissionSet()
        if role:
            perms.update(role.permissions)
        perms.update(self.custom_permissions)
        perms -= self.denied_permissions
        return perms

    def can(self, permission: Permission) -> bool:
        return self.effective_permissions().grants(permission)


class PeerPermissions:
    """Central permission store for a conference.

    Usage::

        pp = PeerPermissions()
        pp.set_role("alice", "moderator")
        pp.grant("bob", Permission.SHARE_SCREEN)
        pp.deny("charlie", Permission.CHAT)

        assert pp.can("alice", Permission.KICK_PEER)
        assert pp.can("bob", Permission.SHARE_SCREEN)
        assert not pp.can("charlie", Permission.CHAT)
    """

    def __init__(self, default_role: str = "participant"):
        self._default_role = default_role
        self._entries: dict[str, PeerPermissionEntry] = {}
        self._roles: dict[str, Role] = dict(BUILTIN_ROLES)
        self._owner: str | None = None

    def define_role(self, name: str, role: Role) -> None:
        """Register a custom role."""
        self._roles[name] = role

    def set_role(self, peer_id: str, role_name: str) -> None:
        """Assign a role to a peer."""
        self._entry(peer_id).role = role_name

    def grant(self, peer_id: str, *permissions: Permission) -> None:
        """Grant additional permissions to a peer."""
        self._entry(peer_id).custom_permissions.update(permissions)

    def deny(self, peer_id: str, *permissions: Permission) -> None:
        """Explicitly deny permissions to a peer."""
        self._entry(peer_id).denied_permissions.update(permissions)

    def set_owner(self, peer_id: str) -> None:
        """Mark a peer as the room owner (unrestricted)."""
        entry = self._entry(peer_id)
        entry.is_owner = True
        self._owner = peer_id

    def can(self, peer_id: str, permission: Permission) -> bool:
        """Check if a peer has a specific permission."""
        return self._entry(peer_id).can(permission)

    def get_entry(self, peer_id: str) -> PeerPermissionEntry:
        return self._entry(peer_id)

    def remove(self, peer_id: str) -> None:
        """Remove a peer from the store."""
        self._entries.pop(peer_id, None)

    @property
    def owner(self) -> str | None:
        return self._owner

    def _entry(self, peer_id: str) -> PeerPermissionEntry:
        if peer_id not in self._entries:
            self._entries[peer_id] = PeerPermissionEntry(
                peer_id=peer_id,
                role=self._default_role,
            )
        return self._entries[peer_id]


__all__ = [
    "Permission",
    "PermissionSet",
    "Role",
    "PeerPermissionEntry",
    "PeerPermissions",
    "ROLE_ADMIN",
    "ROLE_MODERATOR",
    "ROLE_PRESENTER",
    "ROLE_PARTICIPANT",
    "ROLE_LISTENER",
    "BUILTIN_ROLES",
]
