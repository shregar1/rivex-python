from __future__ import annotations

try:
    import rivex_core as _rc
    HAS_CORE = hasattr(_rc, "PyConnectionPool")
except ImportError:
    _rc = None
    HAS_CORE = False


class ConnectionPool:
    def __init__(self, pool_size: int = 3):
        self._pool_size = pool_size
        if HAS_CORE:
            self._core = _rc.PyConnectionPool(pool_size)
        else:
            self._core = None
        self._connections: dict[int, dict[str, str | bool]] = {}
        self._next_id = 0
        self._round_robin: list[int] = []
        self._rr_index = 0

    def register(self, url: str) -> int:
        if self._core:
            return self._core.register(url)
        self._next_id += 1
        cid = self._next_id
        self._connections[cid] = {"url": url, "connected": False}
        self._round_robin.append(cid)
        return cid

    def next(self) -> int | None:
        if self._core:
            return self._core.next()
        if not self._round_robin:
            return None
        cid = self._round_robin[self._rr_index % len(self._round_robin)]
        self._rr_index += 1
        return cid

    def mark_disconnected(self, id: int) -> None:
        if self._core:
            self._core.mark_disconnected(id)
            return
        conn = self._connections.get(id)
        if conn:
            conn["connected"] = False

    def mark_connected(self, id: int) -> None:
        if self._core:
            self._core.mark_connected(id)
            return
        conn = self._connections.get(id)
        if conn:
            conn["connected"] = True

    def remove(self, id: int) -> None:
        if self._core:
            self._core.remove(id)
        self._connections.pop(id, None)
        self._round_robin = [c for c in self._round_robin if c != id]

    def active_count(self) -> int:
        if self._core:
            return self._core.active_count()
        return sum(1 for c in self._connections.values() if c.get("connected"))

    def total_count(self) -> int:
        if self._core:
            return self._core.total_count()
        return len(self._connections)
