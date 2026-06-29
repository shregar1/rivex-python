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
        self._shutting_down = True
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
        if self._core:
            return self._core.is_drain_expired()
        return False

    def connection_closed(self) -> None:
        if self._core:
            self._core.connection_closed()

    def register_connection(self, connection_id: int, conn: object) -> None:
        self._connections[connection_id] = conn

    def remove_connection(self, connection_id: int) -> None:
        self._connections.pop(connection_id, None)
        self.connection_closed()

    @property
    def shutting_down(self) -> bool:
        if self._core:
            return self._core.shutting_down
        return self._shutting_down

    def reset(self) -> None:
        self._shutting_down = False
        if self._core:
            self._core.reset()
