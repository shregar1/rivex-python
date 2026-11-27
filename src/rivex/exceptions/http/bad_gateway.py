"""502 Bad Gateway Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IBadGatewayException(RivexException, ABC):
    """Interface base for 502 Bad Gateway exceptions."""

    status_code: int = HTTPStatus.BAD_GATEWAY
    code: str = ExceptionCode.BAD_GATEWAY
    message: str = ExceptionMessage.BAD_GATEWAY


class BadGatewayException(IBadGatewayException):
    """Generic 502 Bad Gateway exception."""

    pass


__all__ = ["IBadGatewayException", "BadGatewayException"]
