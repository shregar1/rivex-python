from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

try:
    import rivex_core as _rc
    HAS_CORE = hasattr(_rc, "PyGracefulShutdownState")
except ImportError:
    _rc = None
    HAS_CORE = False


class GracefulShutdown:
    def __init__(self, drain_timeout: float = 30.0, on_shutdown: Callable | None = None):
        self._drain_timeout = drain_timeout
        self._on_shutdown = on_shutdown
        if HAS_CORE:
            self._core = _rc.PyGracefulShutdownState(drain_timeout)
        else:
            self._core = None
        self._shutting_down = False
        self._connections: dict[int, object] = {}

    async def start_shutdown(self, notify: Callable | None = None) -> None:
        """Mark the server as shutting down and wait for connections to drain.

        Flips the local ``_shutting_down`` flag and forwards the same state to
        the native core when present. The optional ``notify`` callable is
        awaited once so callers can broadcast a "going away" frame to every
        socket, and the configured ``on_shutdown`` callback is invoked to run
        any registered shutdown hooks. This method then blocks (sleeping in
        100 ms ticks) until either every tracked connection has been removed
        via :meth:`remove_connection` or ``drain_timeout`` seconds elapse.

        Args:
            notify: Optional awaitable invoked once with the literal string
                ``"shutdown"`` before waiting for drains. Errors raised by
                ``notify`` are swallowed.
        """
        if self._core:
            self._core.start_shutdown(len(self._connections))
        if notify:
            try:
                await notify("shutdown")
            except Exception:
                pass
        if self._on_shutdown:
            try:
                await self._on_shutdown()
            except Exception:
                pass
        deadline = time.monotonic() + self._drain_timeout
        while self._connections and time.monotonic() < deadline:
            await asyncio.sleep(0.1)

    def is_drain_expired(self) -> bool:
        """Return whether the configured drain timeout has been exceeded.

        Delegates to the native core when present, which tracks the deadline
        itself. The pure-Python fallback does not maintain a deadline and
        therefore always reports ``False`` — the loop in :meth:`start_shutdown`
        is the source of truth for expiry in that path.

        Returns:
            ``True`` when the drain period has elapsed; ``False`` otherwise.
        """

    def connection_closed(self) -> None:
        """Notify the native core that one connection has finished.

        Decrements the native core's connection counter so the
        ``is_drain_expired`` calculation knows the pool has shrunk. The
        pure-Python fallback relies on the local ``_connections`` map being
        updated by :meth:`remove_connection` and has no work to do here.
        """

    def register_connection(self, connection_id: int, conn: object) -> None:
        """Track a new connection so :meth:`start_shutdown` can wait for it.

        Stores ``conn`` (the underlying socket or wrapper) keyed by
        ``connection_id`` so the drain loop knows which connections to wait
        for. The native core's connection count is updated by
        :meth:`start_shutdown`; this method only manages the local map.

        Args:
            connection_id: Numeric id of the WebSocket connection to track.
            conn: Opaque connection handle retained for the lifetime of the
                socket; never inspected by this class.
        """

    def remove_connection(self, connection_id: int) -> None:
        """Drop a connection from the tracked set once it has closed.

        Removes the ``connection_id`` entry from the local map and notifies
        the native core via :meth:`connection_closed` so the drain
        calculation can be updated. Safe to call on unknown ids.

        Args:
            connection_id: Numeric id of the WebSocket connection that just
                closed and should no longer be considered.
        """

    @property
    def shutting_down(self) -> bool:
        """Return whether :meth:`start_shutdown` has been invoked.

        Reads from the native core when present; otherwise returns the
        local ``_shutting_down`` flag.

        Returns:
            ``True`` once a shutdown has been initiated, ``False`` otherwise.
        """
        if self._core:
            return self._core.shutting_down
        return self._shutting_down

    def reset(self) -> None:
        """Clear the shutdown flag so the manager can be reused.

        Resets the local ``_shutting_down`` flag and asks the native core to
        reset its own state. Useful in tests or after a graceful shutdown
        when the same instance is kept around for a future lifecycle.
        """
