"""``rivex.constants.abstraction`` — base constant interface.

Provides ``IConstant``, the base interface for all Rivex constant classes.
"""

from __future__ import annotations

from abc import ABC
from typing import Any


class IConstant(ABC):
    """Base interface for all Rivex constant classes.

    Subclasses inherit helper methods for constant inspection and validation.
    """

    @classmethod
    def values(cls) -> list[Any]:
        """Return all constant values defined on this class."""
        return [
            value
            for name, value in cls.__dict__.items()
            if not name.startswith("_") and not callable(value) and name.isupper()
        ]

    @classmethod
    def keys(cls) -> list[str]:
        """Return all constant property names defined on this class."""
        return [
            name
            for name, value in cls.__dict__.items()
            if not name.startswith("_") and not callable(value) and name.isupper()
        ]

    @classmethod
    def is_valid(cls, value: Any) -> bool:
        """Check if a value matches one of the defined constants."""
        return value in cls.values()


__all__ = ["IConstant"]
