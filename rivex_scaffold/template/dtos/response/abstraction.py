"""Outbound HTTP response DTO base and standard API envelope."""

from __future__ import annotations

import json
import time
from abc import ABC
from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self

from rivex import Field

from dtos.base import ApplicationBaseModel, IDto
from utilities.request_timing import merge_timing_metadata

if TYPE_CHECKING:
    from errors import DomainError


class IResponseDto(IDto, ApplicationBaseModel, ABC):
    """API response bodies."""

    @classmethod
    def validate_payload(cls, data: dict[str, Any]) -> Self:
        return cls.model_validate(data)


class APIResponseStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


def new_transaction_urn(*, kind: str = "txn") -> str:
    """Generate a unique correlation URN for a single API response."""
    return f"urn:{{project_slug}}:{kind}:{time.time_ns()}"


class APIEnvelopeResponse(IResponseDto):
    """Standard success/error envelope returned by the {{project_name}} API."""

    transaction_urn: str = Field(alias="transactionUrn")
    status: str
    response_message: str = Field(alias="responseMessage")
    response_key: str = Field(alias="responseKey")
    errors: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] | list[Any] = Field(default_factory=dict)
    reference_urn: str | None = None

    def to_http_body(self) -> bytes:
        return json.dumps(
            self.model_dump(by_alias=True, mode="json"),
            separators=(",", ":"),
        ).encode()

    @classmethod
    def success(
        cls,
        data: dict[str, Any] | list[Any] | ApplicationBaseModel | None = None,
        *,
        response_message: str = "OK",
        response_key: str = "SUCCESS",
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
        transaction_urn: str | None = None,
    ) -> Self:
        payload: dict[str, Any] | list[Any]
        if data is None:
            payload = {}
        elif isinstance(data, ApplicationBaseModel):
            payload = data.model_dump()
        else:
            payload = data
        return cls(
            transaction_urn=transaction_urn or new_transaction_urn(kind="txn"),
            status=APIResponseStatus.SUCCESS,
            response_message=response_message,
            response_key=response_key,
            errors=[],
            timestamp=datetime.now(timezone.utc),
            metadata=merge_timing_metadata(metadata),
            data=payload,
            reference_urn=reference_urn,
        )

    @classmethod
    def failed(
        cls,
        response_message: str,
        response_key: str,
        *,
        errors: list[dict[str, Any]] | None = None,
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
        data: dict[str, Any] | list[Any] | None = None,
        transaction_urn: str | None = None,
    ) -> Self:
        error_items = list(errors or [{"message": response_message, "code": response_key}])
        return cls(
            transaction_urn=transaction_urn or new_transaction_urn(kind="err"),
            status=APIResponseStatus.FAILED,
            response_message=response_message,
            response_key=response_key,
            errors=error_items,
            timestamp=datetime.now(timezone.utc),
            metadata=merge_timing_metadata(metadata),
            data=data if data is not None else {},
            reference_urn=reference_urn,
        )

    @classmethod
    def from_domain_error(
        cls,
        err: DomainError,
        *,
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        from errors import ValidationError

        error_item: dict[str, Any] = {"message": err.message, "code": err.code}
        if isinstance(err, ValidationError) and err.field:
            error_item["field"] = err.field
        return cls.failed(
            err.message,
            err.code,
            errors=[error_item],
            reference_urn=reference_urn,
            metadata=metadata,
        )

    @classmethod
    def is_envelope_payload(cls, detail: Any) -> bool:
        return isinstance(detail, dict) and "transactionUrn" in detail


def envelope_http_response(
    envelope: APIEnvelopeResponse,
    *,
    status_code: int,
    extra_headers: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a Rivex ASGI response dict from an envelope."""
    headers: list[tuple[str, str]] = [("content-type", "application/json")]
    if extra_headers:
        headers.extend(extra_headers)
    return {
        "status": status_code,
        "headers": headers,
        "body_json": envelope.model_dump(by_alias=True, mode="json"),
    }
