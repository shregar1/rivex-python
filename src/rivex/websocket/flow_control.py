from __future__ import annotations

from rivex.exceptions.http.exceptions import WebSocketDisconnect

try:
    import rivex_core as _rc
    HAS_CORE = hasattr(_rc, "PyBackpressureTracker")
except ImportError:
    _rc = None
    HAS_CORE = False


class BackpressureController:
    def __init__(self, high_water: int = 256, low_water: int = 128):
        self._high_water = high_water
        self._low_water = low_water
        if HAS_CORE:
            self._core = _rc.PyBackpressureTracker(high_water, low_water)
        else:
            self._core = None
        self._pending: dict[int, int] = {}

    def increment(self, connection_id: int) -> bool:
        """Reserve one slot in the per-connection pending window.

        Bumps the pending count for ``connection_id`` and returns whether the
        connection is still under the high-water mark. The native core, when
        present, performs the same atomic increment and returns its decision.

        Args:
            connection_id: Numeric id of the WebSocket connection whose
                pending count should be raised.

        Returns:
            ``True`` while the connection remains under
            ``high_water``; ``False`` once it has reached or exceeded the
            limit so the caller can apply backpressure.
        """
        if self._core:
            return self._core.increment(connection_id)
        count = self._pending.get(connection_id, 0) + 1
        self._pending[connection_id] = count
        return count <= self._high_water

    def decrement(self, connection_id: int) -> None:
        """Release one pending slot previously taken by :meth:`increment`.

        Decreases the pending count for ``connection_id`` but floors at zero
        so accidental double-decrements cannot push the counter negative. The
        native core, when present, owns the counter and is updated in place.

        Args:
            connection_id: Numeric id of the WebSocket connection whose
                pending count should be lowered.
        """
        if self._core:
            self._core.decrement(connection_id)
            return
        count = self._pending.get(connection_id, 0)
        if count > 0:
            self._pending[connection_id] = count - 1

    def is_throttled(self, connection_id: int) -> bool:
        """Return whether ``connection_id`` is currently above the high-water mark.

        Reads from the native core when available; otherwise compares the
        stored pending count against ``high_water``.

        Args:
            connection_id: Numeric id of the WebSocket connection to check.

        Returns:
            ``True`` once the pending count has reached or exceeded
            ``high_water``; ``False`` otherwise.
        """
        if self._core:
            return self._core.is_throttled(connection_id)
        return self._pending.get(connection_id, 0) >= self._high_water

    def can_resume(self, connection_id: int) -> bool:
        """Return whether a throttled connection has drained back to the low-water mark.

        Reads from the native core when available; otherwise compares the
        stored pending count against ``low_water``. Used by callers that want
        to know when it is safe to start sending again after backpressure.

        Args:
            connection_id: Numeric id of the WebSocket connection to check.

        Returns:
            ``True`` when the pending count has drained to or below
            ``low_water``.
        """
        if self._core:
            return self._core.can_resume(connection_id)
        return self._pending.get(connection_id, 0) <= self._low_water

    def pending_count(self, connection_id: int) -> int:
        """Return the current pending count for ``connection_id``.

        Delegates to the native core when present; otherwise reads from the
        local ``_pending`` map and returns ``0`` for unknown connections.

        Args:
            connection_id: Numeric id of the WebSocket connection to inspect.

        Returns:
            The number of outstanding (incremented but not yet decremented)
            operations associated with this connection.
        """
        if self._core:
            return self._core.pending_count(connection_id)
        return self._pending.get(connection_id, 0)

    async def check_or_raise(self, connection_id: int) -> None:
        """Raise :class:`WebSocketDisconnect` when the connection is throttled.

        Convenience wrapper around :meth:`is_throttled` for callers that want
        the backpressure signal raised as a connection error instead of
        returning a boolean. The error uses close code ``1009`` ("message
        too big") with a reason explaining the cause.

        Args:
            connection_id: Numeric id of the WebSocket connection to check.

        Raises:
            WebSocketDisconnect: When the connection has reached or exceeded
                ``high_water`` pending messages.
        """
        if self.is_throttled(connection_id):
            raise WebSocketDisconnect(code=1009, reason="backpressure: too many pending messages")

    def remove(self, connection_id: int) -> None:
        """Forget all pending counts for a closed connection.

        Deletes the per-connection counter so a later :meth:`increment` for
        the same id starts fresh. The native core, when present, removes its
        own state. Safe to call on unknown ids.

        Args:
            connection_id: Numeric id of the WebSocket connection whose
                bookkeeping should be discarded.
        """
        if self._core:
            self._core.remove(connection_id)
        self._pending.pop(connection_id, None)

    def clear_all(self) -> None:
        """Reset pending counts for every tracked connection.

        Delegates to the native core when present; otherwise empties the
        local ``_pending`` map. Useful for administrative operations such as
        shutting down or restarting a worker.
        """
        if self._core:
            self._core.clear_all()
        self._pending.clear()
