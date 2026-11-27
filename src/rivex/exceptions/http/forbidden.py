"""403 Forbidden Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IForbiddenException(RivexException, ABC):
    """Interface base for 403 Forbidden exceptions."""

    status_code: int = HTTPStatus.FORBIDDEN
    code: str = ExceptionCode.FORBIDDEN
    message: str = ExceptionMessage.FORBIDDEN


class ForbiddenException(IForbiddenException):
    """Generic 403 Forbidden exception."""

    pass


__all__ = ["IForbiddenException", "ForbiddenException"]
