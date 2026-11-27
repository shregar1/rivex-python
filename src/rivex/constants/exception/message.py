"""``rivex.constants.exception.message`` — standard human-readable error messages.

Defines default ``ExceptionMessage`` strings used across framework exceptions.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.exception.abstraction import IExceptionConstant


class ExceptionMessage(IExceptionConstant):
    """Standard human-readable exception message constants."""

    BAD_REQUEST: Final[str] = "Bad request syntax or payload"
    BAD_INPUT: Final[str] = "Bad input"
    NOT_FOUND: Final[str] = "Resource not found"
    UNAUTHORIZED: Final[str] = "Authorization required"
    INVALID_CREDENTIALS: Final[str] = "Invalid credentials"
    UNAUTHENTICATED: Final[str] = "Authentication required"
    FORBIDDEN: Final[str] = "Access forbidden"
    METHOD_NOT_ALLOWED: Final[str] = "HTTP method not allowed for requested endpoint"
    CONFLICT: Final[str] = "Resource state conflict"
    VALIDATION: Final[str] = "Validation error"
    VALIDATION_ERROR: Final[str] = "Validation error"
    INTERNAL_ERROR: Final[str] = "An internal server error occurred"
    INTERNAL_SERVER: Final[str] = "An internal server error occurred"
    INTERNAL_SERVER_ERROR: Final[str] = "An internal server error occurred"
    UNSUPPORTED_MEDIA_TYPE: Final[str] = "Unsupported media type in Content-Type header"
    PAYLOAD_TOO_LARGE: Final[str] = "Request payload exceeds maximum allowed size"
    UNPROCESSABLE_ENTITY: Final[str] = "Unprocessable entity payload"
    TOO_MANY_REQUESTS: Final[str] = "Rate limit exceeded"
    BAD_GATEWAY: Final[str] = "Bad gateway response from upstream server"
    SERVICE_UNAVAILABLE: Final[str] = "Service temporarily unavailable"
    REQUEST_TIMEOUT: Final[str] = "Request timed out"
    DATABASE_TIMEOUT: Final[str] = "Database operation timed out"
    GATEWAY_TIMEOUT: Final[str] = "Gateway timeout"
    CONNECTION_FAILURE: Final[str] = "Upstream connection failure"
    DUPLICATE_KEY: Final[str] = "Duplicate key constraint violation"
    CONSTRAINT_VIOLATION: Final[str] = "Database constraint violation"
    RESOURCE_NOT_FOUND: Final[str] = "Requested resource not found"
    CONCURRENCY_CONFLICT: Final[str] = "Resource modified by another request"


__all__ = ["ExceptionMessage"]
