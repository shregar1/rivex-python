"""500 Internal Server Error Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IInternalServerException(RivexException, ABC):
    """Interface base for 500 Internal Server Error exceptions."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = ExceptionCode.INTERNAL_ERROR
    message: str = ExceptionMessage.INTERNAL_ERROR


class InternalServerException(IInternalServerException):
    """Generic 500 Internal Server Error exception."""

    pass


__all__ = ["IInternalServerException", "InternalServerException"]
