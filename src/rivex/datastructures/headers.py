from __future__ import annotations

from rivex.native._compat import HAS_CORE
from rivex.native._compat import rc as _rc
from rivex.datastructures.abstraction import IDataStructure


class Headers(IDataStructure):
    """Case-insensitive, dict-like header access. Compatible with FastAPI/Starlette.

    When ``rivex_core`` with ``RustHeadersMap`` is available, the internal
    storage is a Rust-backed case-insensitive map with O(1) lookups.
    Otherwise falls back to the pure-Python O(n) scan.
    """

    __slots__ = ("_map", "_list")

    def __init__(self, raw: list[tuple[str, str]] | None = None):
        if HAS_CORE and hasattr(_rc, "RustHeadersMap"):
            self._map = _rc.RustHeadersMap(raw)
            self._list = None
        else:
            self._map = None
            self._list = list(raw) if raw else []

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the first header value matching ``key`` (case-insensitive).

        ``key`` is matched against stored header names after
        lower-casing both sides, so ``"Content-Type"`` and ``"content-type"``
        hit the same entry. When the same name appears multiple times
        only the first occurrence is returned; use :meth:`getlist` for
        the full collection.

        Args:
            key: Header name to look up.
            default: Returned when no header matches. Defaults to
                ``None``.

        Returns:
            The matching header value, or ``default`` when absent.
        """
        if self._map is not None:
            result = self._map.get(key)
            return result if result is not None else default
        target = key.lower()
        for k, v in self._list:
            if k.lower() == target:
                return v
        return default

    def getlist(self, key: str) -> list[str]:
        """Return every value matching ``key``, in insertion order.

        Headers like ``Set-Cookie`` and ``Accept`` are routinely sent
        more than once per response; :meth:`get` keeps only the first
        copy, so callers that need the full sequence — for example to
        iterate every cookie — must use :meth:`getlist`.

        Args:
            key: Header name to look up. Matched case-insensitively.

        Returns:
            All matching values, possibly empty.
        """
        if self._map is not None:
            return list(self._map.getlist(key))
        target = key.lower()
        return [v for k, v in self._list if k.lower() == target]

    def keys(self) -> list[str]:
        """Return header names in insertion order, with duplicates preserved.

        Unlike a dict, repeated header names appear multiple times — the
        container is list-backed, not dict-backed, to mirror raw HTTP
        semantics.

        Returns:
            Header names as they were originally inserted.
        """
        if self._map is not None:
            return list(self._map.keys())
        return [k for k, _ in self._list]

    def values(self) -> list[str]:
        """Return header values in insertion order.

        The returned list mirrors the original ``(name, value)`` pairs:
        each value appears once per occurrence, even if the name is
        repeated.

        Returns:
            Header values in insertion order.
        """
        if self._map is not None:
            return list(self._map.values())
        return [v for _, v in self._list]

    def items(self) -> list[tuple[str, str]]:
        """Return ``(name, value)`` pairs as a copy of the underlying storage.

        The order, casing and duplicate structure of the original
        insertions are preserved. The returned list is freshly
        allocated, so the caller may mutate it freely without affecting
        this container.

        Returns:
            Header pairs in insertion order.
        """
        if self._map is not None:
            return list(self._map.items())
        return list(self._list)

    def __getitem__(self, key: str) -> str:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __contains__(self, key: str) -> bool:
        if self._map is not None:
            return key in self._map
        return self.get(key) is not None

    def __iter__(self):
        if self._map is not None:
            return iter(self._map.keys())
        return iter(k for k, _ in self._list)

    def __len__(self) -> int:
        if self._map is not None:
            return len(self._map)
        return len(self._list)

    def __repr__(self) -> str:
        if self._map is not None:
            items = self._map.all_items()
            return f"Headers({items!r})"
        return f"Headers({self._list!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Headers):
            if self._map is not None and other._map is not None:
                return self._map.all_items() == other._map.all_items()
            return self._list == other._list
        return NotImplemented


__all__ = ["Headers"]
