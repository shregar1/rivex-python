"""``rivex.exceptions.http`` — HTTP status exception classes package.
"""

from __future__ import annotations

from rivex.exceptions.http.abstraction import IHTTPException
from rivex.exceptions.http.bad_gateway import BadGatewayException, IBadGatewayException
from rivex.exceptions.http.bad_request import BadRequestException, IBadRequestException
from rivex.exceptions.http.conflict import ConflictException, IConflictException
from rivex.exceptions.http.forbidden import ForbiddenException, IForbiddenException
from rivex.exceptions.http.internal_server_error import (
    IInternalServerException,
    InternalServerException,
)
from rivex.exceptions.http.method_not_allowed import (
    IMethodNotAllowedException,
    MethodNotAllowedException,
)
from rivex.exceptions.http.not_found import INotFoundException, NotFoundException
from rivex.exceptions.http.payload_too_large import (
    IPayloadTooLargeException,
    PayloadTooLargeException,
)
from rivex.exceptions.http.service_unavailable import (
    IServiceUnavailableException,
    ServiceUnavailableException,
)
from rivex.exceptions.http.timeout import ITimeoutException, TimeoutException
from rivex.exceptions.http.too_many_requests import (
    ITooManyRequestsException,
    TooManyRequestsException,
)
from rivex.exceptions.http.unauthenticated import (
    IUnauthenticatedException,
    UnauthenticatedException,
)
from rivex.exceptions.http.unauthorized import IUnauthorizedException, UnauthorizedException
from rivex.exceptions.http.unprocessable_entity import (
    IUnprocessableEntityException,
    UnprocessableEntityException,
)
from rivex.exceptions.http.unsupported_media_type import (
    IUnsupportedMediaTypeException,
    UnsupportedMediaTypeException,
)

__all__ = [
    # Interface
    "IHTTPException",
    # 4xx interfaces
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
    # 5xx interfaces
    "IInternalServerException",
    "IBadGatewayException",
    "IServiceUnavailableException",
    # 4xx concrete
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
    # 5xx concrete
    "InternalServerException",
    "BadGatewayException",
    "ServiceUnavailableException",
]
