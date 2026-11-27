"""503 Service Unavailable Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IServiceUnavailableException(RivexException, ABC):
    """Interface base for 503 Service Unavailable exceptions."""

    status_code: int = HTTPStatus.SERVICE_UNAVAILABLE
    code: str = ExceptionCode.SERVICE_UNAVAILABLE
    message: str = ExceptionMessage.SERVICE_UNAVAILABLE


class ServiceUnavailableException(IServiceUnavailableException):
    """Generic 503 Service Unavailable exception."""

    pass


__all__ = ["IServiceUnavailableException", "ServiceUnavailableException"]
