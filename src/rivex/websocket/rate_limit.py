from __future__ import annotations

import time

from rivex.exceptions.http.exceptions import WebSocketDisconnect

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
        """Build the bucket key for a connection under the configured scope.

        Prefixes the numeric or string ``connection_id`` with ``self._scope``
        so different scope values (``"connection"``, ``"user"``, etc.) keep
        independent histories.

        Args:
            connection_id: Identifier of the connection whose bucket key is
                required.

        Returns:
            A scope-prefixed string suitable as a dict key.
        """
        return f"{self._scope}:{connection_id}"

    def check(self, connection_id: int | str) -> bool:
        """Record an attempt and report whether it is within the rate limit.

        Prunes timestamps older than ``window_seconds`` from the per-connection
        history, then accepts the attempt when fewer than ``max_messages`` are
        still inside the window. The native core, when present, performs the
        same check and returns its decision.

        Args:
            connection_id: Identifier of the connection that is attempting
                to send.

        Returns:
            ``True`` if the attempt is within the rate limit, ``False`` if
            it should be rejected.
        """
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
        """Reject the connection if :meth:`check` would reject the attempt.

        Convenience wrapper used by handlers that want the rate-limit
        signal raised as a :class:`WebSocketDisconnect` with close code
        ``1009`` instead of having to inspect a boolean.

        Args:
            connection_id: Identifier of the connection to validate.

        Raises:
            WebSocketDisconnect: When the rate limit would reject the
                attempt.
        """
        if not self.check(connection_id):
            raise WebSocketDisconnect(code=1009, reason="rate limit exceeded")

    def reset(self, connection_id: int | str) -> None:
        """Forget the rate-limit history for a single connection.

        Clears the in-memory bucket for ``connection_id`` and asks the native
        core, when present, to do the same. Safe to call on unknown ids.

        Args:
            connection_id: Identifier whose bucket should be cleared.
        """
        if self._core:
            self._core.reset(str(connection_id))
        self._buckets.pop(self._key(connection_id), None)

    def remaining(self, connection_id: int | str) -> int:
        """Return how many more attempts ``connection_id`` can make right now.

        Computes the number of timestamps still inside the rolling window
        and subtracts that count from ``max_messages``, clamped at zero.
        Delegates to the native core when present.

        Args:
            connection_id: Identifier of the connection to query.

        Returns:
            The number of further attempts allowed in the current window.
        """
        if self._core:
            return self._core.remaining(str(connection_id))
        key = self._key(connection_id)
        now = time.monotonic()
        history = [t for t in self._buckets.get(key, []) if now - t < self._window]
        return max(0, self._max_messages - len(history))
