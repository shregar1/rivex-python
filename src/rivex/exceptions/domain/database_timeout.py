"""``rivex.exceptions.domain.database_timeout`` — database timeout domain exception.
"""

from __future__ import annotations

from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.http.timeout import ITimeoutException


class DatabaseTimeoutException(ITimeoutException):
    """Raised when a database operation exceeds its time limit."""

    code: str = ExceptionCode.DATABASE_TIMEOUT
    message: str = ExceptionMessage.DATABASE_TIMEOUT


__all__ = ["DatabaseTimeoutException"]
