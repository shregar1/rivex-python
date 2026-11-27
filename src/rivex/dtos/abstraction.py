"""``rivex.dtos.abstraction`` — base DTO interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IDTO(ABC):
    """Base interface for all Data Transfer Objects in the Rivex framework.

    Every DTO must be serializable to a plain Python dict and JSON bytes.
    """

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dict representation."""

    @abstractmethod
    def to_json(self) -> bytes:
        """Return UTF-8 encoded JSON bytes."""


__all__ = ["IDTO"]
