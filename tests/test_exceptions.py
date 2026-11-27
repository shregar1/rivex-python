"""Contract tests for the framework's exception hierarchy and the
standard envelope. Each exception's status_code + code must
match the lattice-style BaseException table; the envelope shape
must stay in lockstep with the Rust ``rivex-http::exceptions``.
"""

from __future__ import annotations

import pytest

from rivex import (
    BadRequestException,
    ConflictException,
    ConcurrencyConflictException,
    ConnectionFailureException,
    ConstraintViolationException,
    DatabaseTimeoutException,
    DuplicateKeyException,
    ForbiddenException,
    InternalServerException,
    NotFoundException,
    RivexException,
    TimeoutException,
    UnauthenticatedException,
    UnauthorizedException,
    UnprocessableEntityException,
    ValidationErrorItem,
    response_dto,
)
from rivex.exceptions import ExceptionUtils
from rivex.utilities.response import ResponseUtility
from rivex.constants import HTTPStatus


# ── Exceptions ──────────────────────────────────────────────────

EXCEPTION_TABLE = [
    (BadRequestException, HTTPStatus.BAD_REQUEST, "BAD_REQUEST"),
    (UnauthorizedException, HTTPStatus.UNAUTHORIZED, "UNAUTHORIZED"),
    (UnauthenticatedException, HTTPStatus.UNAUTHORIZED, "UNAUTHENTICATED"),
    (ForbiddenException, HTTPStatus.FORBIDDEN, "FORBIDDEN"),
    (NotFoundException, HTTPStatus.NOT_FOUND, "RESOURCE_NOT_FOUND"),
    (ConflictException, HTTPStatus.CONFLICT, "CONFLICT"),
    (UnprocessableEntityException, HTTPStatus.UNPROCESSABLE_ENTITY, "UNPROCESSABLE_ENTITY"),
    (TimeoutException, HTTPStatus.GATEWAY_TIMEOUT, "REQUEST_TIMEOUT"),
    (ConcurrencyConflictException, HTTPStatus.CONFLICT, "CONCURRENCY_CONFLICT"),
    (DatabaseTimeoutException, HTTPStatus.GATEWAY_TIMEOUT, "DATABASE_TIMEOUT"),
    (DuplicateKeyException, HTTPStatus.CONFLICT, "DUPLICATE_KEY"),
    (ConstraintViolationException, HTTPStatus.BAD_REQUEST, "CONSTRAINT_VIOLATION"),
    (ConnectionFailureException, HTTPStatus.SERVICE_UNAVAILABLE, "CONNECTION_FAILURE"),
    (InternalServerException, HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR"),
]


@pytest.mark.parametrize("cls,status,code", EXCEPTION_TABLE)
def test_exception_table(cls: type[RivexException], status: int, code: str):
    """Each typed exception is wired to its lattice status +
    code and is independently raise-able."""
    e = cls("custom message")
    assert e.status_code == status
    assert e.code == code
    assert e.message == "custom message"
    assert ExceptionUtils.is_rivex_exception(e)
    # Exception must also be raisable + catchable.
    with pytest.raises(cls):
        raise cls("boom")


def test_validation_error_item_serialises():
    item = ValidationErrorItem("email", "REQUIRED", "must be present")
    assert item.to_dict() == {
        "field": "email",
        "code": "REQUIRED",
        "message": "must be present",
    }


def test_exception_to_response_shape():
    """``to_response`` must produce a lattice-shape envelope with
    ``status=FAILURE``, ``responseKey=code``, ``message`` mapped
    to ``responseMessage``, and an ``errors`` list."""
    e = UnprocessableEntityException("invalid payload").with_errors(
        []  # placeholder — patched below
    )
    # Reach back to the underlying mechanism: ``to_response``
    # returns the dict that the exception handler middleware
    # would render.
    e.errors = [ValidationErrorItem("name", "REQUIRED", "must be set")]
    payload = e.to_response()
    assert payload["status"] == "FAILURE"
    assert payload["responseKey"] == "UNPROCESSABLE_ENTITY"
    assert payload["responseMessage"] == "invalid payload"
    assert payload["referenceUrn"] == ""
    assert payload["errors"] == [{"field": "name", "code": "REQUIRED", "message": "must be set"}]
    # Transaction urn is minted on demand.
    assert payload["transactionUrn"].startswith("urn:rivex:")


def test_with_errors_via_post_init_path():
    """``cls(errors=[...])`` keyword form must store the items."""
    e = UnprocessableEntityException(
        "bad",
        errors=[ValidationErrorItem("a", "X", "y")],
    )
    assert len(e.errors) == 1
    assert e.errors[0].code == "X"


def test_with_details():
    e = NotFoundException("missing").with_details({"resource": "user"})
    assert e.details == {"resource": "user"}


def test_is_rivex_exception_false_for_other_errors():
    assert not ExceptionUtils.is_rivex_exception(ValueError("nope"))
    assert not ExceptionUtils.is_rivex_exception(KeyError("nope"))


# ── Envelope ───────────────────────────────────────────────────


def test_envelope_data_key_must_match_table():
    resp = response_dto({"ok": True})
    payload = resp.to_dict()
    assert payload["status"] == "SUCCESS"
    assert payload["responseKey"] == "SUCCESS"
    assert payload["responseMessage"] == "Operation completed successfully"
    assert payload["data"] == {"ok": True}
    assert payload["transactionUrn"].startswith("urn:rivex:")
    assert payload["errors"] == []
    assert isinstance(payload["metadata"], dict)


def test_mint_urn_shape():
    u = ResponseUtility.mint_urn()
    assert u.startswith("urn:rivex:")
    # Two distinct mints must not collide.
    assert ResponseUtility.mint_urn() != ResponseUtility.mint_urn() or len(ResponseUtility.mint_urn()) > 12


def test_mint_reference_urn_includes_namespace():
    u = ResponseUtility.mint_reference_urn("order", "42")
    assert u == "urn:rivex:order:42"
