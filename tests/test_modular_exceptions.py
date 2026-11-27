"""Tests for modular exceptions and user-extended exception interfaces."""

import pytest

from rivex.exceptions import (
    BadGatewayException,
    ExceptionUtils,
    MethodNotAllowedException,
    NotFoundException,
    PayloadTooLargeException,
    RivexException,
    TooManyRequestsException,
    UnsupportedMediaTypeException,
)
from rivex.exceptions.http.bad_gateway import IBadGatewayException
from rivex.exceptions.http.bad_request import IBadRequestException
from rivex.exceptions.http.conflict import IConflictException
from rivex.exceptions.http.forbidden import IForbiddenException
from rivex.exceptions.http.internal_server_error import IInternalServerException
from rivex.exceptions.http.method_not_allowed import IMethodNotAllowedException
from rivex.exceptions.http.not_found import INotFoundException
from rivex.exceptions.http.payload_too_large import IPayloadTooLargeException
from rivex.exceptions.http.service_unavailable import IServiceUnavailableException
from rivex.exceptions.http.timeout import ITimeoutException
from rivex.exceptions.http.too_many_requests import ITooManyRequestsException
from rivex.exceptions.http.unauthenticated import IUnauthenticatedException
from rivex.exceptions.http.unauthorized import IUnauthorizedException
from rivex.exceptions.http.unprocessable_entity import IUnprocessableEntityException
from rivex.exceptions.http.unsupported_media_type import IUnsupportedMediaTypeException


# User custom exception extending interface base class via specific module import
class EmailNotFoundException(INotFoundException):
    code: str = "EMAIL_NOT_FOUND"
    message: str = "Specified email address could not be found"


class UserAlreadyExistsException(IConflictException):
    code: str = "USER_ALREADY_EXISTS"
    message: str = "User account already exists"


def test_interface_exception_inheritance():
    exc = EmailNotFoundException()
    assert exc.status_code == 404
    assert exc.code == "EMAIL_NOT_FOUND"
    assert isinstance(exc, INotFoundException)
    assert isinstance(exc, RivexException)
    assert ExceptionUtils.is_rivex_exception(exc) is True


def test_generic_not_found_exception():
    exc = NotFoundException("Item missing")
    assert exc.status_code == 404
    assert exc.code == "RESOURCE_NOT_FOUND"
    assert exc.message == "Item missing"
    assert isinstance(exc, INotFoundException)


def test_custom_conflict_exception():
    exc = UserAlreadyExistsException()
    assert exc.status_code == 409
    assert exc.code == "USER_ALREADY_EXISTS"
    response = exc.to_response()
    assert response["status"] == "FAILURE"
    assert response["responseKey"] == "USER_ALREADY_EXISTS"


def test_all_interfaces_exist():
    interfaces = [
        IBadRequestException,
        IUnauthorizedException,
        IUnauthenticatedException,
        IForbiddenException,
        INotFoundException,
        IMethodNotAllowedException,
        IConflictException,
        IPayloadTooLargeException,
        IUnsupportedMediaTypeException,
        IUnprocessableEntityException,
        ITooManyRequestsException,
        IInternalServerException,
        IBadGatewayException,
        IServiceUnavailableException,
        ITimeoutException,
    ]
    assert len(interfaces) == 15


def test_new_status_exceptions():
    assert MethodNotAllowedException().status_code == 405
    assert PayloadTooLargeException().status_code == 413
    assert UnsupportedMediaTypeException().status_code == 415
    assert TooManyRequestsException().status_code == 429
    assert BadGatewayException().status_code == 502
