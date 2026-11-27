"""429 Too Many Requests Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class ITooManyRequestsException(RivexException, ABC):
    """Interface base for 429 Too Many Requests exceptions."""

    status_code: int = HTTPStatus.TOO_MANY_REQUESTS
    code: str = ExceptionCode.TOO_MANY_REQUESTS
    message: str = ExceptionMessage.TOO_MANY_REQUESTS


class TooManyRequestsException(ITooManyRequestsException):
    """Generic 429 Too Many Requests exception."""

    pass


__all__ = ["ITooManyRequestsException", "TooManyRequestsException"]
