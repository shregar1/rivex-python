"""409 Conflict Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IConflictException(RivexException, ABC):
    """Interface base for 409 Conflict exceptions."""

    status_code: int = HTTPStatus.CONFLICT
    code: str = ExceptionCode.CONFLICT
    message: str = ExceptionMessage.CONFLICT


class ConflictException(IConflictException):
    """Generic 409 Conflict exception."""

    pass


__all__ = ["IConflictException", "ConflictException"]
