"""``rivex.exceptions.abstraction`` — base exception interface.

Provides ``IException``, the base interface for all Rivex exceptions.
"""

from __future__ import annotations

from abc import ABC
from typing import Any


class IException(Exception, ABC):
    """Base interface for all Rivex exception classes."""

    status_code: int
    code: str
    message: str

    def to_response(self) -> dict[str, Any]:
        """Render exception to standard Rivex error envelope dictionary."""
        raise NotImplementedError


__all__ = ["IException"]
