"""Tests for the standardised response DTO builder.

Mirrors the contract on the Rust side: ``ResponseDTO`` / ``HTTPResponse``.
"""

from __future__ import annotations

import json

from rivex import (
    HTTPResponse,
    HTTPStatus,
    ResponseDTO,
    response_dto,
)
from rivex.utilities.response import ResponseUtility


def test_envelope_carries_data_field():
    dto = ResponseDTO.success({"k": "v"})
    assert dto.status == "SUCCESS"
    assert dto.data == {"k": "v"}
    assert dto.transaction_urn.startswith("urn:rivex:")
    assert "T" in dto.timestamp


def test_envelope_builder_success():
    resp = response_dto({"items": [1, 2, 3]}, message="Ok")
    assert resp.status_code == 200
    body = json.loads(resp.to_json())
    assert body["status"] == "SUCCESS"
    assert body["responseMessage"] == "Ok"
    assert body["data"] == {"items": [1, 2, 3]}


def test_envelope_builder_failed():
    resp = response_dto(
        status_code=404,
        response_key="NOT_FOUND",
        message="Resource missing",
        errors=[{"message": "id 42 not found"}],
    )
    assert resp.status_code == 404
    body = json.loads(resp.to_json())
    assert body["status"] == "FAILURE"
    assert body["responseKey"] == "NOT_FOUND"
    assert body["errors"] == [{"message": "id 42 not found"}]
    assert body["data"] is None


def test_envelope_reference_urn_forwarded():
    ref = "urn:rivex:ref:order:123"
    dto = ResponseDTO.success({"ok": True}, reference_urn=ref)
    assert dto.reference_urn == ref
    body = dto.to_dict()
    assert body["referenceUrn"] == ref


def test_envelope_auto_stamps_iso8601_timestamp():
    dto = ResponseDTO.success({"a": 1})
    assert "T" in dto.timestamp


def test_envelope_custom_metadata():
    dto = ResponseDTO.success({"a": 1}, metadata={"trace_id": "abc"})
    assert dto.metadata == {"trace_id": "abc"}


def test_mint_urn_format():
    u = ResponseUtility.mint_urn()
    parts = u.split(":")
    assert parts[0] == "urn"
    assert parts[1] == "rivex"
    assert len(parts) >= 4
    assert all(p for p in parts)
