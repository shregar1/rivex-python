"""``rivex.exceptions.domain.concurrency_conflict`` — concurrency conflict domain exception.
"""

from __future__ import annotations

from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.http.conflict import IConflictException


class ConcurrencyConflictException(IConflictException):
    """Raised when an optimistic locking concurrency conflict is detected."""

    code: str = ExceptionCode.CONCURRENCY_CONFLICT
    message: str = ExceptionMessage.CONCURRENCY_CONFLICT


__all__ = ["ConcurrencyConflictException"]
