"""``rivex.constants.exception.status`` — typed HTTP status constants.

Backed directly by the native Rust ``RivexErrorCode`` PyO3 class.
"""

from __future__ import annotations

from typing import Final

from rivex.constants._rust import RivexErrorCode
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.exception.abstraction import IExceptionConstant


class ExceptionStatus(IExceptionConstant):
    """Associated HTTP status integers and Rust core integration."""

    # ── Status integers (referenced from HTTPStatus) ─────────────
    OK: Final[int] = HTTPStatus.OK
    CREATED: Final[int] = HTTPStatus.CREATED
    ACCEPTED: Final[int] = HTTPStatus.ACCEPTED
    NO_CONTENT: Final[int] = HTTPStatus.NO_CONTENT
    BAD_REQUEST: Final[int] = HTTPStatus.BAD_REQUEST
    UNAUTHORIZED: Final[int] = HTTPStatus.UNAUTHORIZED
    FORBIDDEN: Final[int] = HTTPStatus.FORBIDDEN
    NOT_FOUND: Final[int] = HTTPStatus.NOT_FOUND
    METHOD_NOT_ALLOWED: Final[int] = HTTPStatus.METHOD_NOT_ALLOWED
    CONFLICT: Final[int] = HTTPStatus.CONFLICT
    PAYLOAD_TOO_LARGE: Final[int] = HTTPStatus.PAYLOAD_TOO_LARGE
    UNSUPPORTED_MEDIA_TYPE: Final[int] = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    UNPROCESSABLE_ENTITY: Final[int] = HTTPStatus.UNPROCESSABLE_ENTITY
    TOO_MANY_REQUESTS: Final[int] = HTTPStatus.TOO_MANY_REQUESTS
    INTERNAL_SERVER_ERROR: Final[int] = HTTPStatus.INTERNAL_SERVER_ERROR
    BAD_GATEWAY: Final[int] = HTTPStatus.BAD_GATEWAY
    SERVICE_UNAVAILABLE: Final[int] = HTTPStatus.SERVICE_UNAVAILABLE
    GATEWAY_TIMEOUT: Final[int] = HTTPStatus.GATEWAY_TIMEOUT

    Native = RivexErrorCode


__all__ = ["ExceptionStatus"]
