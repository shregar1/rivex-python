"""``rivex.enums.abstraction`` — base enum interface.

Provides ``IEnum``, the abstract base class for all Rivex enum types.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class IEnum(Enum):
    """Base interface for all Rivex enum classes."""

    @classmethod
    def values(cls) -> list[Any]:
        """Return all member values defined on this Enum."""
        return [member.value for member in cls]

    @classmethod
    def names(cls) -> list[str]:
        """Return all member names defined on this Enum."""
        return [member.name for member in cls]

    @classmethod
    def is_valid(cls, value: Any) -> bool:
        """True if value matches one of the enum member values."""
        return value in cls.values()


__all__ = ["IEnum"]
