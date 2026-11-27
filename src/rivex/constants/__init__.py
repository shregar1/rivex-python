"""``rivex.constants`` — framework-wide constants package.

Re-exports all constants from the ``rivex.constants.api``,
``rivex.constants.exception``, and ``rivex.constants.regex`` sub-packages,
plus the legacy presets (CacheTTL, Pagination, APIStatus).

Usage::

    # New modular imports
    from rivex.constants.api import HTTPMethod, MediaType, Header
    from rivex.constants.exception import Error, ExceptionCode, ExceptionMessage
    from rivex.constants.regex import SecurityKeyRegex, PiiRegex, InjectionRegex

    # Backward-compatible flat imports
    from rivex.constants import (
        APIStatus,
        CacheTTL,
        ContentType,
        HTTPHeader,
        HTTPMethod,
        HTTPStatus,
        Pagination,
    )
"""
from __future__ import annotations

from enum import Enum
from typing import Final

# Re-export from subpackages
from rivex.constants.abstraction import IConstant
from rivex.constants.api.abstraction import IAPIConstant
from rivex.constants.api.envelope import ApiResponseKey, ApiStatus
from rivex.constants.api.header import Header as HTTPHeader
from rivex.constants.api.header import Header
from rivex.constants.api.http_method import HTTPMethod
from rivex.constants.api.media_type import MediaType as ContentType
from rivex.constants.api.media_type import MediaType
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.request_entity import RequestEntity
from rivex.constants.api.response_entity import ResponseEntity
from rivex.constants.auth import AuthConfigConstant
from rivex.constants.db import AuditColumn
from rivex.constants.encoding import ContentEncoding, Encoding, HashAlgorithm
from rivex.constants.exception.abstraction import IExceptionConstant
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.key import ExceptionKey
from rivex.constants.exception.message import ExceptionMessage
from rivex.constants.exception.status import ExceptionStatus
from rivex.constants.otp import OTP
from rivex.constants.regex.abstraction import IRegexConstant
from rivex.constants.regex.injection import InjectionRegex
from rivex.constants.regex.patterns import Regex
from rivex.constants.regex.pii import PiiRegex
from rivex.constants.regex.security_key import SecurityKeyRegex
from rivex.constants.auth import (
    AuthRoleConstant,
    AuthSchemeConstant,
    AuthTokenConstant,
    IAuthConstant,
)
from rivex.constants.context import Context
from rivex.constants.crypto import Encryption, Hashing, ICryptoConstant
from rivex.constants.environment import Environment
from rivex.constants.jwt import JWT
from rivex.constants.lookup import ILookupConstant, MimeType
from rivex.constants.observability import (
    IObservabilityConstant,
    LogLevelConstant,
    MetricTypeConstant,
    TraceStateConstant,
)
from rivex.constants.websocket import (
    IWebSocketConstant,
    WebSocketDisconnectConstant,
    WebSocketFrameConstant,
    WebSocketStateConstant,
)


# ── Presets ─────────────────────────────────────────────────────────

class CacheTTL(IConstant):
    """TTL presets (in seconds)."""

    FIVE_SECONDS: Final[int] = 5
    ONE_MINUTE: Final[int] = 60
    FIVE_MINUTES: Final[int] = 300
    FIFTEEN_MINUTES: Final[int] = 900
    ONE_HOUR: Final[int] = 3600
    ONE_DAY: Final[int] = 86400


class Pagination(IConstant):
    """Framework-wide pagination defaults."""

    DEFAULT_PAGE: Final[int] = 1
    DEFAULT_LIMIT: Final[int] = 20
    MAX_LIMIT: Final[int] = 100
    DEFAULT_SORT_ORDER: Final[str] = "DESC"


class ResponseStatus(str, Enum):
    """Coarse-grained result state for ``api_status`` response fields."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PENDING = "PENDING"

    @classmethod
    def from_http(cls, code: int) -> ResponseStatus:
        """Map a numeric HTTP status code to a :class:`ResponseStatus`."""
        if 200 <= code < 300:
            return cls.SUCCESS
        if code in (
            HTTPStatus.BAD_REQUEST,
            HTTPStatus.UNAUTHORIZED,
            HTTPStatus.FORBIDDEN,
            HTTPStatus.NOT_FOUND,
            HTTPStatus.CONFLICT,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            HTTPStatus.TOO_MANY_REQUESTS,
        ):
            return cls.FAILURE
        return cls.PENDING


__all__ = [
    # Base interfaces
    "IConstant",
    "IAPIConstant",
    "IExceptionConstant",
    "IRegexConstant",
    # Subpackages / new classes
    "Header",
    "HTTPMethod",
    "MediaType",
    "RequestEntity",
    "ResponseEntity",
    "ExceptionStatus",
    "ExceptionCode",
    "ExceptionKey",
    "ExceptionMessage",
    "ApiStatus",
    "ApiResponseKey",
    "IRegexConstant",
    "Regex",
    "SecurityKeyRegex",
    "PiiRegex",
    "InjectionRegex",
    "OTP",
    # Domain constant groups
    "IAuthConstant",
    "AuthConfigConstant",
    "AuthTokenConstant",
    "AuthSchemeConstant",
    "AuthRoleConstant",
    "Context",
    "ICryptoConstant",
    "Encryption",
    "Environment",
    "Hashing",
    "ILookupConstant",
    "JWT",
    "MimeType",
    "ContentEncoding",
    "Encoding",
    "HashAlgorithm",
    "AuditColumn",
    "IObservabilityConstant",
    "LogLevelConstant",
    "MetricTypeConstant",
    "TraceStateConstant",
    "IWebSocketConstant",
    "WebSocketFrameConstant",
    "WebSocketStateConstant",
    "WebSocketDisconnectConstant",
    # Backward compatibility aliases & presets
    "ResponseStatus",
    "CacheTTL",
    "ContentType",
    "HTTPHeader",
    "HTTPStatus",
    "Pagination",
]
