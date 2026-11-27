"""``rivex.constants.exception.code`` — standard machine-readable error codes.

Defines all ``ExceptionCode`` strings used across framework error responses.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.exception.abstraction import IExceptionConstant


class ExceptionCode(IExceptionConstant):
    """Standard machine-readable error code string constants."""

    DOMAIN_ERROR: Final[str] = "DOMAIN_ERROR"
    BAD_REQUEST: Final[str] = "BAD_REQUEST"
    BAD_INPUT: Final[str] = "BAD_INPUT"
    NOT_FOUND: Final[str] = "NOT_FOUND"
    UNAUTHORIZED: Final[str] = "UNAUTHORIZED"
    UNAUTHENTICATED: Final[str] = "UNAUTHENTICATED"
    FORBIDDEN: Final[str] = "FORBIDDEN"
    METHOD_NOT_ALLOWED: Final[str] = "METHOD_NOT_ALLOWED"
    CONFLICT: Final[str] = "CONFLICT"
    PAYLOAD_TOO_LARGE: Final[str] = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE: Final[str] = "UNSUPPORTED_MEDIA_TYPE"
    VALIDATION_ERROR: Final[str] = "VALIDATION_ERROR"
    VALIDATION: Final[str] = "VALIDATION_ERROR"
    UNPROCESSABLE_ENTITY: Final[str] = "UNPROCESSABLE_ENTITY"
    TOO_MANY_REQUESTS: Final[str] = "TOO_MANY_REQUESTS"
    INTERNAL_SERVER_ERROR: Final[str] = "INTERNAL_SERVER_ERROR"
    INTERNAL_SERVER: Final[str] = "INTERNAL_SERVER_ERROR"
    INTERNAL_ERROR: Final[str] = "INTERNAL_ERROR"
    BAD_GATEWAY: Final[str] = "BAD_GATEWAY"
    SERVICE_UNAVAILABLE: Final[str] = "SERVICE_UNAVAILABLE"
    GATEWAY_TIMEOUT: Final[str] = "GATEWAY_TIMEOUT"
    REQUEST_TIMEOUT: Final[str] = "REQUEST_TIMEOUT"
    DATABASE_TIMEOUT: Final[str] = "DATABASE_TIMEOUT"
    CONNECTION_FAILURE: Final[str] = "CONNECTION_FAILURE"
    RESOURCE_NOT_FOUND: Final[str] = "RESOURCE_NOT_FOUND"
    DUPLICATE_KEY: Final[str] = "DUPLICATE_KEY"
    CONSTRAINT_VIOLATION: Final[str] = "CONSTRAINT_VIOLATION"
    CONCURRENCY_CONFLICT: Final[str] = "CONCURRENCY_CONFLICT"
    PROHIBITED_ID_PARAMETER: Final[str] = "PROHIBITED_ID_PARAMETER"
    MALICIOUS_INPUT_DETECTED: Final[str] = "MALICIOUS_INPUT_DETECTED"

    # Granular bad-input codes (driven by ``validate_*`` utility helpers).
    BAD_INPUT_EMAIL: Final[str] = "BAD_INPUT_EMAIL"
    BAD_INPUT_PASSWORD: Final[str] = "BAD_INPUT_PASSWORD"
    BAD_INPUT_URN: Final[str] = "BAD_INPUT_URN"
    BAD_INPUT_URL: Final[str] = "BAD_INPUT_URL"
    BAD_INPUT_ENUM: Final[str] = "BAD_INPUT_ENUM"
    BAD_INPUT_PAGINATION: Final[str] = "BAD_INPUT_PAGINATION"
    BAD_INPUT_DATE_TIME: Final[str] = "BAD_INPUT_DATE_TIME"
    BAD_INPUT_NUMERIC: Final[str] = "BAD_INPUT_NUMERIC"
    BAD_INPUT_STRING: Final[str] = "BAD_INPUT_STRING"
    BAD_INPUT_DECIMAL: Final[str] = "BAD_INPUT_DECIMAL"
    BAD_INPUT_ALPHANUMERIC: Final[str] = "BAD_INPUT_ALPHANUMERIC"
    BAD_INPUT_SLUG: Final[str] = "BAD_INPUT_SLUG"
    BAD_INPUT_PHONE: Final[str] = "BAD_INPUT_PHONE"
    BAD_INPUT_TIMEZONE: Final[str] = "BAD_INPUT_TIMEZONE"
    BAD_INPUT_FILE_NAME: Final[str] = "BAD_INPUT_FILE_NAME"

    # Granular not-found codes (resource-type-specific 404s).
    NOT_FOUND_USER: Final[str] = "NOT_FOUND_USER"
    NOT_FOUND_TENANT: Final[str] = "NOT_FOUND_TENANT"
    NOT_FOUND_ITEM: Final[str] = "NOT_FOUND_ITEM"
    NOT_FOUND_URN: Final[str] = "NOT_FOUND_URN"
    NOT_FOUND_ID: Final[str] = "NOT_FOUND_ID"
    NOT_FOUND_CODE: Final[str] = "NOT_FOUND_CODE"


__all__ = ["ExceptionCode"]
