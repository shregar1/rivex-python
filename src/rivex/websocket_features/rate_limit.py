from __future__ import annotations

import time

from rivex.core.exceptions import WebSocketDisconnect

try:
    import rivex_core as _rc
    HAS_CORE = hasattr(_rc, "PyRateLimiter")
except ImportError:
    _rc = None
    HAS_CORE = False


class RateLimiter:
    def __init__(
        self,
        max_messages: int = 100,
        window_seconds: float = 10.0,
        scope: str = "connection",
    ):
        self._max_messages = max_messages
        self._window = window_seconds
        self._scope = scope
        self._buckets: dict[str, list[float]] = {}
        if HAS_CORE:
            self._core = _rc.PyRateLimiter(max_messages, window_seconds)
        else:
            self._core = None

    def _key(self, connection_id: int | str) -> str:
        return f"{self._scope}:{connection_id}"

    def check(self, connection_id: int | str) -> bool:
        if self._core:
            return self._core.check(str(connection_id))
        key = self._key(connection_id)
        now = time.monotonic()
        history = self._buckets.setdefault(key, [])
        history[:] = [t for t in history if now - t < self._window]
        if len(history) >= self._max_messages:
            return False
        history.append(now)
        return True

    async def check_or_raise(self, connection_id: int | str) -> None:
        if not self.check(connection_id):
            raise WebSocketDisconnect(code=1009, reason="rate limit exceeded")

    def reset(self, connection_id: int | str) -> None:
        if self._core:
            self._core.reset(str(connection_id))
        self._buckets.pop(self._key(connection_id), None)

    def remaining(self, connection_id: int | str) -> int:
        if self._core:
            return self._core.remaining(str(connection_id))
        key = self._key(connection_id)
        now = time.monotonic()
        history = [t for t in self._buckets.get(key, []) if now - t < self._window]
        return max(0, self._max_messages - len(history))
