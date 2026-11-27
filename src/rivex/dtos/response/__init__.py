"""``rivex.dtos.response`` — Response DTO sub-package.

Organized into grouped sub-packages:
- ``abstraction``: ``IResponseDTO``, ``ResponseDTO``
- ``content``: ``HTTPResponse``, ``JsonResponse``, ``HtmlResponse``, ``PlainTextResponse``, ``XmlResponse``
- ``stream``: ``StreamingResponse``, ``EventSourceResponse``
- ``transfer``: ``RedirectResponse``, ``FileResponse``
- ``exception``: ``IExceptionResponseDTO`` and specialized exception response DTOs
"""

from __future__ import annotations

from rivex.dtos.response.abstraction import IResponseDTO, ResponseDTO, response_dto
from rivex.dtos.response.content import HtmlResponse, HTTPResponse, JsonResponse, PlainTextResponse, XmlResponse
from rivex.dtos.response.exception import (
    BadGatewayExceptionResponse,
    BadRequestExceptionResponse,
    ConcurrencyConflictExceptionResponse,
    ConflictExceptionResponse,
    ConnectionFailureExceptionResponse,
    ConstraintViolationExceptionResponse,
    DatabaseTimeoutExceptionResponse,
    DuplicateKeyExceptionResponse,
    ForbiddenExceptionResponse,
    IExceptionResponseDTO,
    InternalServerExceptionResponse,
    MethodNotAllowedExceptionResponse,
    NotFoundExceptionResponse,
    PayloadTooLargeExceptionResponse,
    RivexExceptionResponse,
    ServiceUnavailableExceptionResponse,
    TimeoutExceptionResponse,
    TooManyRequestsExceptionResponse,
    UnauthenticatedExceptionResponse,
    UnauthorizedExceptionResponse,
    UnprocessableEntityExceptionResponse,
    UnsupportedMediaTypeExceptionResponse,
)
from rivex.dtos.response.stream import EventSourceResponse, StreamingResponse
from rivex.dtos.response.transfer import FileResponse, RedirectResponse

__all__ = [
    "IResponseDTO",
    "ResponseDTO",
    "response_dto",
    "HTTPResponse",
    "JsonResponse",
    "HtmlResponse",
    "PlainTextResponse",
    "XmlResponse",
    "StreamingResponse",
    "EventSourceResponse",
    "RedirectResponse",
    "FileResponse",
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
