"""413 Payload Too Large Exceptions."""

from __future__ import annotations

from abc import ABC

from rivex.constants import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.base import RivexException


class IPayloadTooLargeException(RivexException, ABC):
    """Interface base for 413 Payload Too Large exceptions."""

    status_code: int = HTTPStatus.PAYLOAD_TOO_LARGE
    code: str = ExceptionCode.PAYLOAD_TOO_LARGE
    message: str = ExceptionMessage.PAYLOAD_TOO_LARGE


class PayloadTooLargeException(IPayloadTooLargeException):
    """Generic 413 Payload Too Large exception."""

    pass


__all__ = ["IPayloadTooLargeException", "PayloadTooLargeException"]
