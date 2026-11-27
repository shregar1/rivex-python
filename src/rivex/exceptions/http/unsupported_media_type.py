"""415 Unsupported Media Type Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IUnsupportedMediaTypeException(RivexException, ABC):
    """Interface base for 415 Unsupported Media Type exceptions."""

    status_code: int = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    code: str = ExceptionCode.UNSUPPORTED_MEDIA_TYPE
    message: str = ExceptionMessage.UNSUPPORTED_MEDIA_TYPE


class UnsupportedMediaTypeException(IUnsupportedMediaTypeException):
    """Generic 415 Unsupported Media Type exception."""

    pass


__all__ = ["IUnsupportedMediaTypeException", "UnsupportedMediaTypeException"]
