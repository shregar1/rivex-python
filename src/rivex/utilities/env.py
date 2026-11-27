"""``rivex.utilities.env`` — environment variable access utility."""

from __future__ import annotations

import os
from typing import Optional, Union

from rivex.utilities.abstraction import LayeredUtility


class EnvUtility(LayeredUtility):
    """Read values from the process environment (populated via dotenv in main)."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Return the env value for ``key``, or ``default`` when unset/empty."""
        value = os.environ.get(key)
        if value is None or value == "":
            return default
        return value

    def require(self, key: str) -> str:
        """Return the env value for ``key`` or raise ``KeyError`` when missing."""
        value = self.get(key)
        if value is None:
            raise KeyError(f"Required environment variable '{key}' is not set")
        return value

    def get_int(self, key: str, default: Optional[int] = None) -> Optional[int]:
        """Return ``key`` parsed as ``int`` (or ``default`` when unset/empty)."""
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(
                f"Environment variable '{key}' must be an integer, got {value!r}"
            ) from exc

    def get_bytes(
        self,
        key: str,
        default: Optional[Union[str, bytes]] = None,
        *,
        encoding: str = "utf-8",
    ) -> Optional[bytes]:
        """Return ``key`` as UTF-8 bytes (or ``default`` encoded when unset)."""
        value = self.get(key)
        if value is None:
            if default is None:
                return None
            if isinstance(default, bytes):
                return default
            return default.encode(encoding)
        return value.encode(encoding)

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Return ``key`` parsed as bool. Accepts ``1/0/true/false/yes/no/on/off`` (case-insensitive)."""
        value = self.get(key)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "EnvUtility"


__all__ = ["EnvUtility"]
