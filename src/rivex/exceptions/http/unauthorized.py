"""401 Unauthorized Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IUnauthorizedException(RivexException, ABC):
    """Interface base for 401 Unauthorized exceptions."""

    status_code: int = HTTPStatus.UNAUTHORIZED
    code: str = ExceptionCode.UNAUTHORIZED
    message: str = ExceptionMessage.UNAUTHORIZED


class UnauthorizedException(IUnauthorizedException):
    """Generic 401 Unauthorized exception."""

    pass


__all__ = ["IUnauthorizedException", "UnauthorizedException"]
