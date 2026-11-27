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
        """Add a new outgoing connection slot for ``url`` to the pool.

        Allocates a numeric id and records the endpoint. When the Rust core is
        available this is delegated to it; otherwise the id is generated
        locally, the connection is marked disconnected, and it is appended to
        the round-robin queue used by :meth:`next`.

        Args:
            url: The WebSocket URL the slot will eventually connect to.

        Returns:
            The numeric connection id assigned to the new slot.
        """
        if self._core:
            return self._core.register(url)
        self._next_id += 1
        cid = self._next_id
        self._connections[cid] = {"url": url, "connected": False}
        self._round_robin.append(cid)
        return cid

    def next(self) -> int | None:
        """Pick the next connection id from the round-robin queue.

        Cycles through the registered slots in insertion order so load is
        spread evenly across the pool. The Rust core performs the same
        round-robin selection natively when present.

        Returns:
            The next connection id to use, or ``None`` if the pool is empty.
        """
        if self._core:
            return self._core.next()
        if not self._round_robin:
            return None
        cid = self._round_robin[self._rr_index % len(self._round_robin)]
        self._rr_index += 1
        return cid

    def mark_disconnected(self, id: int) -> None:
        """Mark the connection slot as disconnected so it stops being served.

        Updates the ``connected`` flag on the slot's metadata so
        :meth:`active_count` can exclude it from active totals. The native
        core, when present, performs the equivalent bookkeeping in-place.

        Args:
            id: Numeric connection id returned from :meth:`register`.
                Unknown ids are silently ignored.
        """
        if self._core:
            self._core.mark_disconnected(id)
            return
        conn = self._connections.get(id)
        if conn:
            conn["connected"] = False

    def mark_connected(self, id: int) -> None:
        """Mark the connection slot as currently active.

        Flips the ``connected`` flag on the slot's metadata so it counts
        toward :meth:`active_count` and is a candidate for outbound traffic.
        When the native core is available it owns the state transition.

        Args:
            id: Numeric connection id returned from :meth:`register`.
                Unknown ids are silently ignored.
        """
        if self._core:
            self._core.mark_connected(id)
            return
        conn = self._connections.get(id)
        if conn:
            conn["connected"] = True

    def remove(self, id: int) -> None:
        """Drop a connection slot from the pool entirely.

        Removes the slot's metadata and prunes it from the round-robin queue
        so it is never returned by :meth:`next` again. The native core, when
        present, removes its own state.

        Args:
            id: Numeric connection id returned from :meth:`register``.
                Unknown ids are silently ignored.
        """
        if self._core:
            self._core.remove(id)
        self._connections.pop(id, None)
        self._round_robin = [c for c in self._round_robin if c != id]

    def active_count(self) -> int:
        """Return the number of pool slots currently marked connected.

        Delegates to the native core when present; otherwise iterates the
        local metadata dict and counts entries whose ``connected`` flag is
        truthy.

        Returns:
            The number of active connections in the pool.
        """
        if self._core:
            return self._core.active_count()
        return sum(1 for c in self._connections.values() if c.get("connected"))

    def total_count(self) -> int:
        """Return the total number of slots registered in the pool.

        Counts every connection registered through :meth:`register` regardless
        of whether it is currently connected or disconnected.

        Returns:
            The number of slots currently tracked, which may exceed
            :meth:`active_count`.
        """
        if self._core:
            return self._core.total_count()
        return len(self._connections)
