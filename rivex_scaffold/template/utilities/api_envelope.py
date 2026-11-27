"""Helpers for serializing standard API envelopes to HTTP responses."""

from __future__ import annotations

import json
from typing import Any

from rivex.exceptions.http.exceptions import HTTPException

from dtos.response.abstraction import APIEnvelopeResponse, envelope_http_response


def http_exception_detail(envelope: APIEnvelopeResponse) -> dict[str, Any]:
    """Serialize an envelope for ``HTTPException.detail`` (flat JSON object)."""
    return envelope.model_dump(by_alias=True, mode="json")


def envelope_from_http_exception(exc: HTTPException, *, reference_urn: str | None = None) -> APIEnvelopeResponse:
    """Normalize any HTTP exception detail into the standard envelope."""
    detail = exc.detail
    if APIEnvelopeResponse.is_envelope_payload(detail):
        return APIEnvelopeResponse.model_validate(detail)
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or "Request failed")
        code = str(detail.get("code") or "HTTP_ERROR")
        return APIEnvelopeResponse.failed(message, code, reference_urn=reference_urn)
    return APIEnvelopeResponse.failed(str(detail), "HTTP_ERROR", reference_urn=reference_urn)


def render_http_exception(
    exc: HTTPException,
    *,
    reference_urn: str | None = None,
) -> dict[str, Any]:
    envelope = envelope_from_http_exception(exc, reference_urn=reference_urn)
    headers = list(exc.headers.items()) if exc.headers else None
    return envelope_http_response(envelope, status_code=exc.status_code, extra_headers=headers)


def render_envelope_bytes(envelope: APIEnvelopeResponse) -> bytes:
    return envelope.to_http_body()


def parse_envelope_json(raw: bytes | str) -> APIEnvelopeResponse | None:
    try:
        text = raw.decode() if isinstance(raw, bytes) else raw
        payload = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not APIEnvelopeResponse.is_envelope_payload(payload):
        return None
    return APIEnvelopeResponse.model_validate(payload)
