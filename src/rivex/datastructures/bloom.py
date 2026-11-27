"""``rivex.datastructures.bloom`` — BloomFilter wrapper.

Backed directly by native Rust PyO3 ``BloomFilter`` class.
"""

from __future__ import annotations

from rivex.native._compat import HAS_CORE
from rivex.native._compat import rc as _rc
from rivex.datastructures.abstraction import IDataStructure


class BloomFilter(IDataStructure):
    """High-performance probabilistic set membership container."""

    def __init__(self, capacity: int = 10000, fp_rate: float = 0.01):
        if HAS_CORE and hasattr(_rc, "BloomFilter"):
            self._impl = _rc.BloomFilter(capacity, fp_rate)
        else:
            self._set = set()
            self._impl = None

    def add(self, item: str) -> None:
        """Record ``item`` in the filter so future :meth:`contains` calls can detect it.

        Adds the underlying item hashes to the configured Rust-backed bit
        array when ``rivex_core`` is available; otherwise falls back to a
        plain Python ``set`` membership record. The operation is
        idempotent — re-adding an item is harmless.

        Args:
            item: The string to register. Non-string inputs raise the
                error of the underlying implementation.
        """
        if self._impl is not None:
            self._impl.add(item)
        else:
            self._set.add(item)

    def contains(self, item: str) -> bool:
        """Return ``True`` if ``item`` was previously passed to :meth:`add`.

        The answer can be a false positive (probabilistic structure) but
        never a false negative: an item that was once added is always
        reported as present. When the Rust core is unavailable the
        answer is exact — backed by a plain Python ``set``.

        Args:
            item: The string to test for membership.

        Returns:
            ``True`` when ``item`` is *probably* in the filter,
            ``False`` when it is definitely not.
        """
        if self._impl is not None:
            return self._impl.contains(item)
        return item in self._set

    def __contains__(self, item: str) -> bool:
        return self.contains(item)


__all__ = ["BloomFilter"]
