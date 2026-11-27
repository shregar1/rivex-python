"""``rivex.exceptions.domain.duplicate_key`` — duplicate key domain exception.
"""

from __future__ import annotations

from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.http.conflict import IConflictException


class DuplicateKeyException(IConflictException):
    """Raised when an entity with a unique identifier already exists."""

    code: str = ExceptionCode.DUPLICATE_KEY
    message: str = ExceptionMessage.DUPLICATE_KEY


__all__ = ["DuplicateKeyException"]
