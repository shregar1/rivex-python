"""``rivex.datastructures.ring_buffer`` — RingBuffer wrapper.

Backed directly by native Rust PyO3 ``RingBuffer`` class.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from rivex.native._compat import HAS_CORE
from rivex.native._compat import rc as _rc
from rivex.datastructures.abstraction import IDataStructure


class RingBuffer(IDataStructure):
    """Fixed-capacity ring buffer data structure."""

    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        if HAS_CORE and hasattr(_rc, "RingBuffer"):
            self._impl = _rc.RingBuffer(capacity)
        else:
            self._deque = deque(maxlen=capacity)
            self._impl = None

    def push(self, item: Any) -> None:
        """Append ``item`` to the back of the buffer, evicting the oldest when full.

        When the underlying storage has reached ``capacity`` the push
        evicts the oldest element to make room. With ``rivex_core``
        installed, the call is dispatched to the native Rust
        implementation; otherwise it delegates to a
        :class:`collections.deque` with ``maxlen=capacity``.

        Args:
            item: The value to store. Anything serialisable through the
                chosen backend works.
        """
        if self._impl is not None:
            self._impl.push(item)
        else:
            self._deque.append(item)

    def pop(self) -> Any | None:
        """Remove and return the oldest element still in the buffer.

        The buffer acts as a FIFO queue: :meth:`pop` returns items in
        the same order they were :meth:`push`-ed. Returns ``None`` when
        the buffer is empty rather than raising, which is convenient for
        drain loops in background workers.

        Returns:
            The oldest element, or ``None`` if the buffer is empty.
        """
        if self._impl is not None:
            return self._impl.pop()
        return self._deque.popleft() if self._deque else None

    def __len__(self) -> int:
        if self._impl is not None:
            return len(self._impl)
        return len(self._deque)


__all__ = ["RingBuffer"]
