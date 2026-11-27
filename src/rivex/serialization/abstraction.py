"""``rivex.serialization.abstraction`` — base serialization interface.

Provides ``ISerializer``, the base interface protocol for all Rivex serialization engines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ISerializer(ABC):
    """Base interface for Rivex serializers/codecs."""

    @abstractmethod
    def serialize(self, value: Any) -> bytes:
        """Serialize a Python object into bytes."""
        raise NotImplementedError

    @abstractmethod
    def deserialize(self, data: bytes | str) -> Any:
        """Deserialize raw bytes or string into a Python object."""
        raise NotImplementedError


__all__ = ["ISerializer"]
