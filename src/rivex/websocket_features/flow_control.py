from __future__ import annotations

from rivex.exceptions import WebSocketDisconnect

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
        if self._core:
            return self._core.increment(connection_id)
        count = self._pending.get(connection_id, 0) + 1
        self._pending[connection_id] = count
        return count <= self._high_water

    def decrement(self, connection_id: int) -> None:
        if self._core:
            self._core.decrement(connection_id)
            return
        count = self._pending.get(connection_id, 0)
        if count > 0:
            self._pending[connection_id] = count - 1

    def is_throttled(self, connection_id: int) -> bool:
        if self._core:
            return self._core.is_throttled(connection_id)
        return self._pending.get(connection_id, 0) >= self._high_water

    def can_resume(self, connection_id: int) -> bool:
        if self._core:
            return self._core.can_resume(connection_id)
        return self._pending.get(connection_id, 0) <= self._low_water

    def pending_count(self, connection_id: int) -> int:
        if self._core:
            return self._core.pending_count(connection_id)
        return self._pending.get(connection_id, 0)

    async def check_or_raise(self, connection_id: int) -> None:
        if self.is_throttled(connection_id):
            raise WebSocketDisconnect(code=1009, reason="backpressure: too many pending messages")

    def remove(self, connection_id: int) -> None:
        if self._core:
            self._core.remove(connection_id)
        self._pending.pop(connection_id, None)

    def clear_all(self) -> None:
        if self._core:
            self._core.clear_all()
        self._pending.clear()
