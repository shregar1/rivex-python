"""401 Unauthenticated Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IUnauthenticatedException(RivexException, ABC):
    """Interface base for 401 Unauthenticated exceptions."""

    status_code: int = HTTPStatus.UNAUTHORIZED
    code: str = ExceptionCode.UNAUTHENTICATED
    message: str = ExceptionMessage.UNAUTHENTICATED


class UnauthenticatedException(IUnauthenticatedException):
    """Generic 401 Unauthenticated exception."""

    pass


__all__ = ["IUnauthenticatedException", "UnauthenticatedException"]
