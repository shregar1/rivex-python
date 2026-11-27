"""504 Gateway Timeout Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class ITimeoutException(RivexException, ABC):
    """Interface base for 504 Gateway Timeout exceptions."""

    status_code: int = HTTPStatus.GATEWAY_TIMEOUT
    code: str = ExceptionCode.REQUEST_TIMEOUT
    message: str = ExceptionMessage.REQUEST_TIMEOUT


class TimeoutException(ITimeoutException):
    """Generic 504 Gateway Timeout exception."""

    pass


__all__ = ["ITimeoutException", "TimeoutException"]
