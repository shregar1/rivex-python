"""``rivex.exceptions`` package — HTTP and domain exception hierarchy.

Provides abstract interface base classes (``INotFoundException``,
``IBadRequestException``, etc.), default concrete implementations
(``NotFoundException``, ``BadRequestException``, etc.), and helper utilities.
"""

from __future__ import annotations

from typing import Any

from rivex.exceptions.abstraction import IException
from rivex.exceptions.base import RivexException, ValidationErrorItem
from rivex.exceptions.domain import (
    ConcurrencyConflictException,
    ConnectionFailureException,
    ConstraintViolationException,
    DatabaseTimeoutException,
    DuplicateKeyException,
    IDomainException,
)
from rivex.exceptions.http import (
    BadGatewayException,
    BadRequestException,
    ConflictException,
    ForbiddenException,
    IBadGatewayException,
    IBadRequestException,
    IConflictException,
    IForbiddenException,
    IHTTPException,
    IInternalServerException,
    IMethodNotAllowedException,
    INotFoundException,
    IPayloadTooLargeException,
    IServiceUnavailableException,
    ITimeoutException,
    ITooManyRequestsException,
    IUnauthenticatedException,
    IUnauthorizedException,
    IUnprocessableEntityException,
    IUnsupportedMediaTypeException,
    InternalServerException,
    MethodNotAllowedException,
    NotFoundException,
    PayloadTooLargeException,
    ServiceUnavailableException,
    TimeoutException,
    TooManyRequestsException,
    UnauthenticatedException,
    UnauthorizedException,
    UnprocessableEntityException,
    UnsupportedMediaTypeException,
)


class ExceptionUtils:
    """Utility helpers for inspecting exceptions."""

    @staticmethod
    def is_rivex_exception(value: Any) -> bool:
        """True when ``value`` is a :class:`RivexException` instance."""
        return isinstance(value, RivexException)


__all__ = [
    # Interfaces — base
    "IException",
    "IHTTPException",
    "IDomainException",
    # Interfaces — HTTP 4xx
    "IBadRequestException",
    "IUnauthenticatedException",
    "IForbiddenException",
    "INotFoundException",
    "IMethodNotAllowedException",
    "IConflictException",
    "IPayloadTooLargeException",
    "IUnsupportedMediaTypeException",
    "IUnprocessableEntityException",
    "ITooManyRequestsException",
    "IUnauthorizedException",
    "ITimeoutException",
    # Interfaces — HTTP 5xx
    "IInternalServerException",
    "IBadGatewayException",
    "IServiceUnavailableException",
    # Base class & validation
    "RivexException",
    "ValidationErrorItem",
    # Utils
    "ExceptionUtils",
    # Concrete — HTTP 4xx
    "BadRequestException",
    "UnauthenticatedException",
    "ForbiddenException",
    "NotFoundException",
    "MethodNotAllowedException",
    "ConflictException",
    "PayloadTooLargeException",
    "UnsupportedMediaTypeException",
    "UnprocessableEntityException",
    "TooManyRequestsException",
    "UnauthorizedException",
    "TimeoutException",
    # Concrete — HTTP 5xx
    "InternalServerException",
    "BadGatewayException",
    "ServiceUnavailableException",
    # Concrete — domain
    "ConcurrencyConflictException",
    "ConnectionFailureException",
    "ConstraintViolationException",
    "DatabaseTimeoutException",
    "DuplicateKeyException",
]
