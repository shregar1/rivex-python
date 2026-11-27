"""``rivex.constants.api.http_status`` — HTTP status code numeric constants.

Provides ``HTTPStatus``, backed by ``IAPIConstant``.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.api.abstraction import IAPIConstant


class HTTPStatus(IAPIConstant):
    """Numeric HTTP status code constants."""

    OK: Final[int] = 200
    CREATED: Final[int] = 201
    ACCEPTED: Final[int] = 202
    NO_CONTENT: Final[int] = 204
    MOVED_PERMANENTLY: Final[int] = 301
    FOUND: Final[int] = 302
    SEE_OTHER: Final[int] = 303
    TEMPORARY_REDIRECT: Final[int] = 307
    PERMANENT_REDIRECT: Final[int] = 308
    BAD_REQUEST: Final[int] = 400
    VALIDATION: Final[int] = 400
    UNAUTHORIZED: Final[int] = 401
    FORBIDDEN: Final[int] = 403
    NOT_FOUND: Final[int] = 404
    METHOD_NOT_ALLOWED: Final[int] = 405
    CONFLICT: Final[int] = 409
    PAYLOAD_TOO_LARGE: Final[int] = 413
    UNSUPPORTED_MEDIA_TYPE: Final[int] = 415
    UNPROCESSABLE_ENTITY: Final[int] = 422
    TOO_MANY_REQUESTS: Final[int] = 429
    INTERNAL_SERVER_ERROR: Final[int] = 500
    INTERNAL_SERVER: Final[int] = 500
    BAD_GATEWAY: Final[int] = 502
    SERVICE_UNAVAILABLE: Final[int] = 503
    GATEWAY_TIMEOUT: Final[int] = 504


__all__ = ["HTTPStatus"]
