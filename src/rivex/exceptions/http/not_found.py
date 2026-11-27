"""404 Not Found Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class INotFoundException(RivexException, ABC):
    """Interface base for 404 Not Found exceptions.

    Extend this to create custom domain exceptions like ``EmailNotFoundException``.
    """

    status_code: int = HTTPStatus.NOT_FOUND
    code: str = ExceptionCode.RESOURCE_NOT_FOUND
    message: str = ExceptionMessage.RESOURCE_NOT_FOUND


class NotFoundException(INotFoundException):
    """Generic 404 Not Found exception."""

    pass


__all__ = ["INotFoundException", "NotFoundException"]
