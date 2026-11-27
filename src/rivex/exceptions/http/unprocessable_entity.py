"""422 Unprocessable Entity Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IUnprocessableEntityException(RivexException, ABC):
    """Interface base for 422 Unprocessable Entity exceptions."""

    status_code: int = HTTPStatus.UNPROCESSABLE_ENTITY
    code: str = ExceptionCode.UNPROCESSABLE_ENTITY
    message: str = ExceptionMessage.UNPROCESSABLE_ENTITY


class UnprocessableEntityException(IUnprocessableEntityException):
    """Generic 422 Unprocessable Entity exception."""

    pass


__all__ = ["IUnprocessableEntityException", "UnprocessableEntityException"]
