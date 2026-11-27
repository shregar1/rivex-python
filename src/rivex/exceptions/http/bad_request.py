"""400 Bad Request Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IBadRequestException(RivexException, ABC):
    """Interface base for 400 Bad Request exceptions."""

    status_code: int = HTTPStatus.BAD_REQUEST
    code: str = ExceptionCode.BAD_REQUEST
    message: str = ExceptionMessage.BAD_REQUEST


class BadRequestException(IBadRequestException):
    """Generic 400 Bad Request exception."""

    pass


__all__ = ["IBadRequestException", "BadRequestException"]
