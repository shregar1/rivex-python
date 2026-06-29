from __future__ import annotations

from rivex._compat import RC_V2
from rivex._compat import rc as _rc


class Headers:
    """Case-insensitive, dict-like header access. Compatible with FastAPI/Starlette."""

    __slots__ = ("_list",)

    def __init__(self, raw: list[tuple[str, str]] | None = None):
        self._list = list(raw) if raw else []

    def get(self, key: str, default: str | None = None) -> str | None:
        if RC_V2:
            result = _rc.headers_get(self._list, key)
            return result if result is not None else default
        target = key.lower()
        for k, v in self._list:
            if k.lower() == target:
                return v
        return default

    def getlist(self, key: str) -> list[str]:
        if RC_V2:
            result: list[str] = _rc.headers_get_all(self._list, key)
            return result
        target = key.lower()
        return [v for k, v in self._list if k.lower() == target]

    def keys(self) -> list[str]:
        return [k for k, _ in self._list]

    def values(self) -> list[str]:
        return [v for _, v in self._list]

    def items(self) -> list[tuple[str, str]]:
        return list(self._list)

    def __getitem__(self, key: str) -> str:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __iter__(self):
        return iter(k for k, _ in self._list)

    def __len__(self) -> int:
        return len(self._list)

    def __repr__(self) -> str:
        return f"Headers({self._list!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Headers):
            return self._list == other._list
        return NotImplemented
