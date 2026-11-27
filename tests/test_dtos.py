"""Tests for the ``rivex.dtos`` layer and specialized response DTOs."""

from __future__ import annotations

import json

from rivex.dtos import (
    IDTO,
    BadRequestExceptionResponse,
    ConflictExceptionResponse,
    EventSourceResponse,
    FileResponse,
    HeaderDTO,
    HtmlResponse,
    HTTPResponse,
    JsonResponse,
    NotFoundExceptionResponse,
    PlainTextResponse,
    RedirectResponse,
    ResponseDTO,
    RivexExceptionResponse,
    StreamingResponse,
    ValidationErrorItem,
    XmlResponse,
)
from rivex.exceptions.http.conflict import ConflictException
from rivex.exceptions.http.not_found import INotFoundException


class ItemNotFoundException(INotFoundException):
    code: str = "ITEM_NOT_FOUND"
    message: str = "The requested item was not found"


# ── ValidationErrorItem ────────────────────────────────────────────────────


def test_validation_error_item_to_dict():
    item = ValidationErrorItem(field="email", code="INVALID_FORMAT", message="Not a valid email")
    d = item.to_dict()
    assert d == {"field": "email", "code": "INVALID_FORMAT", "message": "Not a valid email"}


def test_validation_error_item_to_json():
    item = ValidationErrorItem(field="name", code="REQUIRED", message="Name is required")
    payload = json.loads(item.to_json())
    assert payload["field"] == "name"
    assert payload["code"] == "REQUIRED"


# ── ResponseDTO ────────────────────────────────────────────────────


def test_response_envelope_to_dict_keys():
    env = ResponseDTO(
        transaction_urn="urn:rivex:abc:def",
        status="SUCCESS",
        response_key="USER_CREATED",
        response_message="Created",
        timestamp="2024-01-01T00:00:00Z",
        data={"id": "u-1"},
    )
    d = env.to_dict()
    assert d["transactionUrn"] == "urn:rivex:abc:def"
    assert d["status"] == "SUCCESS"
    assert d["responseKey"] == "USER_CREATED"
    assert d["data"] == {"id": "u-1"}
    assert d["errors"] == []
    assert d["metadata"] == {}


def test_response_envelope_to_json_parseable():
    env = ResponseDTO(
        transaction_urn="urn:rivex:1:2",
        status="FAILURE",
        response_key="NOT_FOUND",
        response_message="Not found",
        timestamp="2024-01-01T00:00:00Z",
        errors=[ValidationErrorItem(field="id", code="INVALID", message="Bad id")],
        data=None,
    )
    payload = json.loads(env.to_json())
    assert payload["status"] == "FAILURE"
    assert payload["errors"][0]["field"] == "id"
    assert payload["data"] is None


# ── HTTPResponse ────────────────────────────────────────────────────────


def test_http_response_ok_factory():
    resp = HTTPResponse.ok(data={"id": "u-1"}, response_key="USER_FETCHED")
    assert resp.status_code == 200
    d = resp.to_dict()
    assert d["status"] == "SUCCESS"
    assert d["data"] == {"id": "u-1"}
    assert d["responseKey"] == "USER_FETCHED"


def test_http_response_fail_factory():
    resp = HTTPResponse.fail(
        status_code=422,
        response_key="VALIDATION_FAILED",
        response_message="Payload is invalid",
        errors=[ValidationErrorItem(field="age", code="MUST_BE_POSITIVE", message="Age must be > 0")],
    )
    assert resp.status_code == 422
    d = resp.to_dict()
    assert d["status"] == "FAILURE"
    assert d["errors"][0]["code"] == "MUST_BE_POSITIVE"


def test_http_response_from_exception():
    exc = ItemNotFoundException()
    resp = HTTPResponse.from_exception(exc)
    assert resp.status_code == 404
    d = resp.to_dict()
    assert d["status"] == "FAILURE"
    assert d["responseKey"] == "ITEM_NOT_FOUND"
    assert d["data"] is None


# ── Specialized Response DTOs ──────────────────────────────────────────────


def test_json_response_dto():
    resp = JsonResponse(data={"key": "val"})
    assert resp.status_code == 200
    assert resp.to_headers()["content-type"] == "application/json"
    assert json.loads(resp.to_json()) == {"key": "val"}


def test_html_response_dto():
    resp = HtmlResponse(content="<h1>Hello</h1>")
    assert resp.status_code == 200
    assert resp.to_headers()["content-type"] == "text/html"
    assert resp.to_body() == b"<h1>Hello</h1>"


def test_plain_text_response_dto():
    resp = PlainTextResponse(content="Hello World")
    assert resp.status_code == 200
    assert resp.to_headers()["content-type"] == "text/plain"
    assert resp.to_body() == b"Hello World"


def test_redirect_response_dto():
    resp = RedirectResponse(url="https://example.com/login")
    assert resp.status_code == 307
    assert resp.to_headers()["location"] == "https://example.com/login"


def test_streaming_response_dto():
    resp = StreamingResponse(content=[b"chunk1", b"chunk2"])
    assert resp.status_code == 200
    assert resp.to_headers()["content-type"] == "application/octet-stream"


def test_event_source_response_dto():
    resp = EventSourceResponse(content="sse_stream")
    assert resp.status_code == 200
    headers = resp.to_headers()
    assert headers["content-type"] == "text/event-stream"
    assert headers["cache-control"] == "no-cache"


def test_file_response_dto():
    resp = FileResponse(path="/tmp/test.txt", filename="download.txt")
    assert resp.status_code == 200
    headers = resp.to_headers()
    assert headers["content-disposition"] == 'attachment; filename="download.txt"'


def test_xml_response_dto():
    resp = XmlResponse(content="<root><val>1</val></root>")
    assert resp.status_code == 200
    assert resp.to_headers()["content-type"] == "application/xml"
    assert resp.to_body() == b"<root><val>1</val></root>"


def test_header_dto():
    hd = HeaderDTO.from_dict({"Content-Type": "application/json", "X-Custom": "val"})
    assert isinstance(hd, IDTO)
    assert hd.get("content-type") == "application/json"
    assert hd["x-custom"] == "val"
    assert hd.to_dict() == {"content-type": "application/json", "x-custom": "val"}
    assert hd.to_tuples() == [("content-type", "application/json"), ("x-custom", "val")]
    payload = json.loads(hd.to_json())
    assert payload["content-type"] == "application/json"


def test_conflict_exception_response():
    err = ConflictException(message="Resource already exists", code="RESOURCE_CONFLICT")
    resp = ConflictExceptionResponse.from_conflict_exception(err, reference_urn="urn:ref:123")
    d = resp.to_dict()
    assert d["status"] == "FAILURE"
    assert d["responseMessage"] == "Resource already exists"
    assert d["responseKey"] == "RESOURCE_CONFLICT"
    assert d["referenceUrn"] == "urn:ref:123"


