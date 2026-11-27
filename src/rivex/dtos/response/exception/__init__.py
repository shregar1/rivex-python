"""``rivex.dtos.response.exception`` — Exception response DTOs sub-package.

Provides specialized Exception Response DTOs constructed directly from framework exceptions.
"""

from __future__ import annotations

from rivex.dtos.response.exception.abstraction import IExceptionResponseDTO
from rivex.dtos.response.exception.bad_gateway import BadGatewayExceptionResponse
from rivex.dtos.response.exception.bad_request import BadRequestExceptionResponse
from rivex.dtos.response.exception.concurrency_conflict import ConcurrencyConflictExceptionResponse
from rivex.dtos.response.exception.conflict import ConflictExceptionResponse
from rivex.dtos.response.exception.connection_failure import ConnectionFailureExceptionResponse
from rivex.dtos.response.exception.constraint_violation import ConstraintViolationExceptionResponse
from rivex.dtos.response.exception.database_timeout import DatabaseTimeoutExceptionResponse
from rivex.dtos.response.exception.duplicate_key import DuplicateKeyExceptionResponse
from rivex.dtos.response.exception.forbidden import ForbiddenExceptionResponse
from rivex.dtos.response.exception.generic import RivexExceptionResponse
from rivex.dtos.response.exception.internal_server_error import InternalServerExceptionResponse
from rivex.dtos.response.exception.method_not_allowed import MethodNotAllowedExceptionResponse
from rivex.dtos.response.exception.not_found import NotFoundExceptionResponse
from rivex.dtos.response.exception.payload_too_large import PayloadTooLargeExceptionResponse
from rivex.dtos.response.exception.service_unavailable import ServiceUnavailableExceptionResponse
from rivex.dtos.response.exception.timeout import TimeoutExceptionResponse
from rivex.dtos.response.exception.too_many_requests import TooManyRequestsExceptionResponse
from rivex.dtos.response.exception.unauthenticated import UnauthenticatedExceptionResponse
from rivex.dtos.response.exception.unauthorized import UnauthorizedExceptionResponse
from rivex.dtos.response.exception.unprocessable_entity import UnprocessableEntityExceptionResponse
from rivex.dtos.response.exception.unsupported_media_type import UnsupportedMediaTypeExceptionResponse

__all__ = [
    "IExceptionResponseDTO",
    "ConflictExceptionResponse",
    "BadRequestExceptionResponse",
    "NotFoundExceptionResponse",
    "UnauthorizedExceptionResponse",
    "UnauthenticatedExceptionResponse",
    "ForbiddenExceptionResponse",
    "InternalServerExceptionResponse",
    "MethodNotAllowedExceptionResponse",
    "PayloadTooLargeExceptionResponse",
    "UnsupportedMediaTypeExceptionResponse",
    "UnprocessableEntityExceptionResponse",
    "TooManyRequestsExceptionResponse",
    "TimeoutExceptionResponse",
    "BadGatewayExceptionResponse",
    "ServiceUnavailableExceptionResponse",
    "DuplicateKeyExceptionResponse",
    "ConcurrencyConflictExceptionResponse",
    "DatabaseTimeoutExceptionResponse",
    "ConstraintViolationExceptionResponse",
    "ConnectionFailureExceptionResponse",
    "RivexExceptionResponse",
]
