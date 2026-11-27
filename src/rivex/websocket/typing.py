from __future__ import annotations

import json
import time
from collections.abc import Callable

try:
    import rivex_core as _rc
    HAS_CORE = hasattr(_rc, "PyTypingTracker")
except ImportError:
    _rc = None
    HAS_CORE = False


class TypingIndicators:
    def __init__(
        self,
        throttle_seconds: float = 1.0,
        on_typing: Callable | None = None,
    ):
        self._throttle = throttle_seconds
        self._last_sent: dict[str, float] = {}
        self._on_typing = on_typing
        if HAS_CORE:
            self._core = _rc.PyTypingTracker(throttle_seconds)
        else:
            self._core = None

    async def typing_start(self, room: str, user_id: str, broadcast: Callable) -> None:
        """Broadcast a "typing started" event for ``user_id`` in ``room``.

        Throttles repeated events so the same user does not flood the
        channel: subsequent calls within ``throttle_seconds`` are silently
        dropped, and the native core (when present) applies its own rate
        limit on top. The encoded frame is dispatched through ``broadcast``
        and the optional ``on_typing`` callback is awaited with ``True``.

        Args:
            room: Logical room identifier the event is scoped to.
            user_id: Identifier of the user that started typing.
            broadcast: Awaitable callable used to deliver the encoded
                ``"typing"`` frame to other room members.
        """
        key = f"{room}:{user_id}"
        now = time.monotonic()
        if now - self._last_sent.get(key, 0) < self._throttle:
            return
        if self._core and not self._core.can_send(room, user_id):
            return
        self._last_sent[key] = now
        msg = json.dumps({"type": "typing", "room": room, "user_id": user_id, "status": "start"})
        await broadcast(msg)
        if self._on_typing:
            await self._on_typing(room, user_id, True)

    async def typing_stop(self, room: str, user_id: str, broadcast: Callable) -> None:
        """Broadcast a "typing stopped" event for ``user_id`` in ``room``.

        Forgets the throttling timestamp for the user, updates the native
        core (when present), and dispatches a ``status: "stop"`` frame via
        ``broadcast``. The ``on_typing`` callback is awaited with ``False``
        if one was configured.

        Args:
            room: Logical room identifier the event is scoped to.
            user_id: Identifier of the user that stopped typing.
            broadcast: Awaitable callable used to deliver the encoded
                ``"typing"`` frame to other room members.
        """
        self._last_sent.pop(f"{room}:{user_id}", None)
        if self._core:
            self._core.stop(room, user_id)
        msg = json.dumps({"type": "typing", "room": room, "user_id": user_id, "status": "stop"})
        await broadcast(msg)
        if self._on_typing:
            await self._on_typing(room, user_id, False)

    def is_typing(self, room: str, user_id: str) -> bool:
        """Return whether ``user_id`` is still considered to be typing.

        The pure-Python fallback considers a user typing if their last
        ``typing_start`` is more recent than ``3 * throttle_seconds`` ago.
        The native core, when present, owns the decision and is consulted
        directly.

        Args:
            room: Logical room identifier to inspect.
            user_id: Identifier of the user to check.

        Returns:
            ``True`` if the user is still considered to be typing, ``False``
            otherwise.
        """
        if self._core:
            return self._core.is_typing(room, user_id)
        key = f"{room}:{user_id}"
        now = time.monotonic()
        return now - self._last_sent.get(key, 0) < self._throttle * 3
