"""Contract tests for the framework constants module.

These pin the literal values so the Rust core and the Python mirror
cannot drift. Anything the Rust `rivex-middleware::constants` module
exposes must match the corresponding Python attribute here.
"""

from __future__ import annotations

from rivex.constants import (
    CacheTTL,
    ContentType,
    HTTPHeader,
    HTTPMethod,
    HTTPStatus,
    Pagination,
    ResponseStatus,
)
from rivex import Rivex

import pytest


# ── HTTP method ─────────────────────────────────────────────────────


def test_http_method_constants():
    assert HTTPMethod.GET == "GET"
    assert HTTPMethod.POST == "POST"
    assert HTTPMethod.PUT == "PUT"
    assert HTTPMethod.PATCH == "PATCH"
    assert HTTPMethod.DELETE == "DELETE"
    assert HTTPMethod.OPTIONS == "OPTIONS"
    assert HTTPMethod.HEAD == "HEAD"


@pytest.mark.parametrize("verb", ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
def test_http_method_parse_recognises(verb: str):
    assert HTTPMethod.parse(verb) == verb


@pytest.mark.parametrize("verb", ["get", "trace", "FOOBAR", ""])
def test_http_method_parse_rejects(verb: str):
    assert HTTPMethod.parse(verb) is None


@pytest.mark.parametrize(
    "verb,mutating",
    [
        ("POST", True),
        ("PUT", True),
        ("PATCH", True),
        ("DELETE", True),
        ("GET", False),
        ("HEAD", False),
        ("OPTIONS", False),
    ],
)
def test_http_method_is_mutating(verb: str, mutating: bool):
    assert HTTPMethod.is_mutating(verb) is mutating


# ── HTTP status ─────────────────────────────────────────────────────


def test_http_status_constants():
    assert HTTPStatus.OK == 200
    assert HTTPStatus.CREATED == 201
    assert HTTPStatus.ACCEPTED == 202
    assert HTTPStatus.NO_CONTENT == 204
    assert HTTPStatus.BAD_REQUEST == 400
    assert HTTPStatus.UNAUTHORIZED == 401
    assert HTTPStatus.FORBIDDEN == 403
    assert HTTPStatus.NOT_FOUND == 404
    assert HTTPStatus.CONFLICT == 409
    assert HTTPStatus.UNPROCESSABLE_ENTITY == 422
    assert HTTPStatus.TOO_MANY_REQUESTS == 429
    assert HTTPStatus.PAYLOAD_TOO_LARGE == 413
    assert HTTPStatus.UNSUPPORTED_MEDIA_TYPE == 415
    assert HTTPStatus.INTERNAL_SERVER_ERROR == 500
    assert HTTPStatus.SERVICE_UNAVAILABLE == 503
    assert HTTPStatus.GATEWAY_TIMEOUT == 504


# ── HTTP header ─────────────────────────────────────────────────────


def test_http_header_lowercase():
    assert HTTPHeader.X_REQUEST_ID == "x-request-id"
    assert HTTPHeader.X_CORRELATION_ID == "x-correlation-id"
    assert HTTPHeader.X_TENANT_ID == "x-tenant-id"
    assert HTTPHeader.X_SUBJECT_ID == "x-subject-id"
    assert HTTPHeader.AUTHORIZATION == "authorization"
    assert HTTPHeader.CONTENT_TYPE == "content-type"
    assert HTTPHeader.ACCEPT == "accept"
    assert HTTPHeader.ORIGIN == "origin"
    assert HTTPHeader.COOKIE == "cookie"
    assert HTTPHeader.SET_COOKIE == "set-cookie"
    assert HTTPHeader.LOCATION == "location"


# ── Content type ────────────────────────────────────────────────────


def test_content_type_constants():
    assert ContentType.APPLICATION_JSON == "application/json"
    assert ContentType.MULTIPART_FORM_DATA == "multipart/form-data"
    assert (
        ContentType.APPLICATION_X_WWW_FORM_URLENCODED
        == "application/x-www-form-urlencoded"
    )
    assert ContentType.TEXT_PLAIN == "text/plain"
    assert ContentType.TEXT_HTML == "text/html"
    assert ContentType.APPLICATION_OCTET_STREAM == "application/octet-stream"
    assert ContentType.APPLICATION_PDF == "application/pdf"
    assert ContentType.TEXT_EVENT_STREAM == "text/event-stream"


def test_content_type_default_allow_list():
    assert ContentType.APPLICATION_JSON in ContentType.DEFAULT_MUTATING_ALLOW_LIST
    assert ContentType.TEXT_PLAIN in ContentType.DEFAULT_MUTATING_ALLOW_LIST
    assert "text/xml" not in ContentType.DEFAULT_MUTATING_ALLOW_LIST


# ── Cache TTL ───────────────────────────────────────────────────────


def test_cache_ttl_constants():
    assert CacheTTL.FIVE_SECONDS == 5
    assert CacheTTL.ONE_MINUTE == 60
    assert CacheTTL.FIVE_MINUTES == 300
    assert CacheTTL.FIFTEEN_MINUTES == 900
    assert CacheTTL.ONE_HOUR == 3600
    assert CacheTTL.ONE_DAY == 86400


# ── Pagination ──────────────────────────────────────────────────────


def test_pagination_constants():
    assert Pagination.DEFAULT_PAGE == 1
    assert Pagination.DEFAULT_LIMIT == 20
    assert Pagination.MAX_LIMIT == 100
    assert Pagination.DEFAULT_SORT_ORDER == "DESC"


# ── API status ──────────────────────────────────────────────────────


def test_api_status_strings():
    assert ResponseStatus.SUCCESS.value == "SUCCESS"
    assert ResponseStatus.FAILURE.value == "FAILURE"
    assert ResponseStatus.PENDING.value == "PENDING"


@pytest.mark.parametrize(
    "code,expected",
    [
        (200, ResponseStatus.SUCCESS),
        (201, ResponseStatus.SUCCESS),
        (204, ResponseStatus.SUCCESS),
        (400, ResponseStatus.FAILURE),
        (401, ResponseStatus.FAILURE),
        (403, ResponseStatus.FAILURE),
        (404, ResponseStatus.FAILURE),
        (409, ResponseStatus.FAILURE),
        (422, ResponseStatus.FAILURE),
        (429, ResponseStatus.FAILURE),
        (103, ResponseStatus.PENDING),
        (301, ResponseStatus.PENDING),
        (500, ResponseStatus.PENDING),
        (503, ResponseStatus.PENDING),
    ],
)
def test_api_status_from_http(code: int, expected: ResponseStatus):
    assert ResponseStatus.from_http(code) == expected


# ── Top-level re-export ─────────────────────────────────────────────


def test_constants_are_exported_from_package():
    """The constants must be reachable both as
    ``rivex.constants.X`` and as ``rivex.X`` after re-export."""
    import rivex

    assert rivex.HTTPMethod is HTTPMethod
    assert rivex.HTTPStatus is HTTPStatus
    assert rivex.HTTPHeader is HTTPHeader
    assert rivex.ContentType is ContentType
    assert rivex.CacheTTL is CacheTTL
    assert rivex.Pagination is Pagination
    assert rivex.ResponseStatus is ResponseStatus


# ── Integration with middleware ─────────────────────────────────────


def test_request_validation_uses_content_type_constants():
    """The bundled middleware should accept any value in the constants
    allow-list verbatim — no string drift between core and middleware.
    """
    from rivex.testing.testing import TestClient

    app = Rivex()

    @app.post("/x")
    async def x():
        return {"ok": True}

    from rivex.middleware.middleware_native import RequestValidationMiddleware

    app.add_middleware(RequestValidationMiddleware)

    client = TestClient(app)
    resp = client.post("/x", json={"k": "v"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
