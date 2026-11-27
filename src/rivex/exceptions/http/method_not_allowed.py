"""405 Method Not Allowed Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IMethodNotAllowedException(RivexException, ABC):
    """Interface base for 405 Method Not Allowed exceptions."""

    status_code: int = HTTPStatus.METHOD_NOT_ALLOWED
    code: str = ExceptionCode.METHOD_NOT_ALLOWED
    message: str = ExceptionMessage.METHOD_NOT_ALLOWED


class MethodNotAllowedException(IMethodNotAllowedException):
    """Generic 405 Method Not Allowed exception."""

    pass


__all__ = ["IMethodNotAllowedException", "MethodNotAllowedException"]
