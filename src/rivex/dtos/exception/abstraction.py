"""``rivex.dtos.exception.abstraction`` — base exception DTO interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from rivex.dtos.abstraction import IDTO


class IExceptionDTO(IDTO, ABC):
    """Base interface for all Exception Data Transfer Objects in the Rivex framework."""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Return a dict representation of the exception error details."""


__all__ = ["IExceptionDTO"]
