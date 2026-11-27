"""``rivex.exceptions.domain.constraint_violation`` — constraint violation domain exception.
"""

from __future__ import annotations

from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.http.bad_request import IBadRequestException


class ConstraintViolationException(IBadRequestException):
    """Raised when a database constraint is violated."""

    code: str = ExceptionCode.CONSTRAINT_VIOLATION
    message: str = ExceptionMessage.CONSTRAINT_VIOLATION


__all__ = ["ConstraintViolationException"]
