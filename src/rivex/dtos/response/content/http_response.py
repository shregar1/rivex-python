"""``rivex.dtos.response.http_response`` — final JSON-serializable HTTP response DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.dtos.response.abstraction import IResponseDTO
from rivex.dtos.response.abstraction import ResponseDTO
from rivex.dtos.exception import ValidationErrorItem
from rivex.serialization.serialization import serialize


from rivex.utilities.response import ResponseUtility


@dataclass
class HTTPResponse(IResponseDTO):
    """Fully-formed HTTP response that can be handed directly to any transport layer.

    Attributes:
        envelope:    The :class:`ResponseDTO` body.
        status_code: HTTP status code (default ``200``).
        headers:     Extra HTTP headers to include in the response.
        media_type:  Content-Type value (default ``application/json``).

    The body is always the JSON serialization of ``envelope.to_dict()``.
    """

    envelope: ResponseDTO
    status_code: int = HTTPStatus.OK
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = MediaType.APPLICATION_JSON

    # ── IDTO protocol ──────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return the envelope as a plain Python dict."""
        return self.envelope.to_dict()

    def to_json(self) -> bytes:
        """Return UTF-8 JSON bytes of the envelope."""
        return serialize(self.to_dict())

    # ── Transport helpers ──────────────────────────────────────────────────

    def to_headers(self) -> dict[str, str]:
        """Return a headers dict with Content-Type pre-populated."""
        return {"content-type": self.media_type, **self.headers}

    # ── Factory class-methods ──────────────────────────────────────────────

    @classmethod
    def ok(
        cls,
        data: Any = None,
        *,
        status_code: int = HTTPStatus.OK,
        response_key: str = "SUCCESS",
        response_message: str = "Operation completed successfully",
        metadata: dict[str, Any] | None = None,
        transaction_urn: str | None = None,
        reference_urn: str = "",
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        """Build a **success** :class:`HTTPResponse`."""
        envelope = ResponseDTO(
            transaction_urn=transaction_urn or ResponseUtility.mint_urn(),
            reference_urn=reference_urn,
            status="SUCCESS",
            response_key=response_key,
            response_message=response_message,
            timestamp=ResponseUtility.iso8601_now(),
            metadata=metadata or {},
            data=data,
        )
        return cls(envelope=envelope, status_code=status_code, headers=headers or {})

    @classmethod
    def fail(
        cls,
        *,
        status_code: int = HTTPStatus.BAD_REQUEST,
        response_key: str = ExceptionCode.BAD_REQUEST,
        response_message: str = ExceptionMessage.BAD_REQUEST,
        errors: list[ValidationErrorItem] | None = None,
        metadata: dict[str, Any] | None = None,
        transaction_urn: str | None = None,
        reference_urn: str = "",
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        """Build a **failure** :class:`HTTPResponse` manually."""
        envelope = ResponseDTO(
            transaction_urn=transaction_urn or ResponseUtility.mint_urn(),
            reference_urn=reference_urn,
            status="FAILURE",
            response_key=response_key,
            response_message=response_message,
            errors=list(errors or []),
            timestamp=ResponseUtility.iso8601_now(),
            metadata=metadata or {},
            data=None,
        )
        return cls(envelope=envelope, status_code=status_code, headers=headers or {})

    @classmethod
    def from_exception(
        cls,
        exc: Any,
        *,
        transaction_urn: str | None = None,
        reference_urn: str = "",
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        """Build an :class:`HTTPResponse` directly from a ``RivexException``."""
        errors: list[ValidationErrorItem] = []
        for e in getattr(exc, "errors", []):
            if isinstance(e, ValidationErrorItem):
                errors.append(e)
            elif isinstance(e, dict):
                errors.append(
                    ValidationErrorItem(
                        field=e.get("field", ""),
                        code=e.get("code", ""),
                        message=e.get("message", ""),
                    )
                )

        envelope = ResponseDTO(
            transaction_urn=transaction_urn or ResponseUtility.mint_urn(),
            reference_urn=reference_urn,
            status="FAILURE",
            response_key=getattr(exc, "code", ExceptionCode.INTERNAL_ERROR),
            response_message=getattr(exc, "message", ExceptionMessage.INTERNAL_ERROR) or str(exc),
            errors=errors,
            timestamp=ResponseUtility.iso8601_now(),
            metadata=getattr(exc, "details", None) or {},
            data=None,
        )
        return cls(
            envelope=envelope,
            status_code=getattr(exc, "status_code", HTTPStatus.INTERNAL_SERVER_ERROR),
            headers=headers or {},
        )


__all__ = ["HTTPResponse"]
