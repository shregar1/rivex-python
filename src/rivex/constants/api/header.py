"""``rivex.constants.api.header`` — HTTP header name constants.

Backed directly by the native Rust ``RivexHeader`` PyO3 class.
"""

from __future__ import annotations

from typing import Final

from rivex.constants._rust import RivexHeader
from rivex.constants.api.abstraction import IAPIConstant


class Header(IAPIConstant):
    """Canonical lowercase HTTP header name constants, backed by Rust."""

    CONTENT_TYPE: Final[str] = "content-type"
    CONTENT_LENGTH: Final[str] = "content-length"
    ACCEPT: Final[str] = "accept"
    AUTHORIZATION: Final[str] = "authorization"
    ORIGIN: Final[str] = "origin"
    COOKIE: Final[str] = "cookie"
    SET_COOKIE: Final[str] = "set-cookie"
    LOCATION: Final[str] = "location"
    CACHE_CONTROL: Final[str] = "cache-control"
    ETAG: Final[str] = "etag"
    IF_NONE_MATCH: Final[str] = "if-none-match"
    HOST: Final[str] = "host"
    USER_AGENT: Final[str] = "user-agent"
    REFERER: Final[str] = "referer"

    X_REQUEST_ID: Final[str] = "x-request-id"
    X_CORRELATION_ID: Final[str] = "x-correlation-id"
    X_USER_URN: Final[str] = "x-user-urn"
    X_TRANSACTION_URN: Final[str] = "x-transaction-urn"
    X_REFERENCE_URN: Final[str] = "x-reference-urn"
    X_REFERENCE_ID: Final[str] = "x-reference-id"

    REQUEST_ID: Final[str] = X_REQUEST_ID
    REFERENCE_ID: Final[str] = X_REFERENCE_ID
    REFERENCE_URN: Final[str] = X_REFERENCE_URN
    TRANSACTION_URN_HEADER: Final[str] = X_TRANSACTION_URN
    USER_URN_HEADER: Final[str] = X_USER_URN
    X_TENANT_ID: Final[str] = "x-tenant-id"
    X_SUBJECT_ID: Final[str] = "x-subject-id"
    X_FORWARDED_FOR: Final[str] = "x-forwarded-for"
    X_FORWARDED_PROTO: Final[str] = "x-forwarded-proto"
    X_REAL_IP: Final[str] = "x-real-ip"
    X_API_KEY: Final[str] = "x-api-key"
    IDEMPOTENCY_KEY: Final[str] = "idempotency-key"
    X_HTTP_METHOD_OVERRIDE: Final[str] = "x-http-method-override"

    TRACEPARENT: Final[str] = "traceparent"
    TRACESTATE: Final[str] = "tracestate"
    X_B3_TRACEID: Final[str] = "x-b3-traceid"
    X_B3_SPANID: Final[str] = "x-b3-spanid"
    X_B3_SAMPLED: Final[str] = "x-b3-sampled"

    CONTENT_ENCODING: Final[str] = "content-encoding"
    TRANSFER_ENCODING: Final[str] = "transfer-encoding"
    ACCEPT_ENCODING: Final[str] = "accept-encoding"
    ACCEPT_LANGUAGE: Final[str] = "accept-language"

    STRICT_TRANSPORT_SECURITY: Final[str] = "strict-transport-security"
    X_FRAME_OPTIONS: Final[str] = "x-frame-options"
    X_CONTENT_TYPE_OPTIONS: Final[str] = "x-content-type-options"
    X_XSS_PROTECTION: Final[str] = "x-xss-protection"
    CONTENT_SECURITY_POLICY: Final[str] = "content-security-policy"
    REFERRER_POLICY: Final[str] = "referrer-policy"

    ACCESS_CONTROL_ALLOW_ORIGIN: Final[str] = "access-control-allow-origin"
    ACCESS_CONTROL_ALLOW_METHODS: Final[str] = "access-control-allow-methods"
    ACCESS_CONTROL_ALLOW_HEADERS: Final[str] = "access-control-allow-headers"
    ACCESS_CONTROL_EXPOSE_HEADERS: Final[str] = "access-control-expose-headers"
    ACCESS_CONTROL_MAX_AGE: Final[str] = "access-control-max-age"
    ACCESS_CONTROL_ALLOW_CREDENTIALS: Final[str] = "access-control-allow-credentials"
    ACCESS_CONTROL_REQUEST_METHOD: Final[str] = "access-control-request-method"
    ACCESS_CONTROL_REQUEST_HEADERS: Final[str] = "access-control-request-headers"
    VARY: Final[str] = "vary"

    Native = RivexHeader


__all__ = ["Header"]
