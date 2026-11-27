"""``rivex.dtos.response.abstraction`` — base response DTO interface and standard response DTO.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Self

from rivex.dtos.abstraction import IDTO
from rivex.dtos.exception import ValidationErrorItem
from rivex.serialization.serialization import serialize


class IResponseDTO(IDTO, ABC):
    """Base interface for all Response Data Transfer Objects in the Rivex framework.

    Extends ``IDTO`` with status_code and headers inspection protocols.
    """

    @property
    @abstractmethod
    def status_code(self) -> int:
        """Return the HTTP status code."""

    @abstractmethod
    def to_headers(self) -> dict[str, str]:
        """Return HTTP headers dict."""


@dataclass
class ResponseDTO(IDTO):
    """Standard Rivex response DTO.

    Represents the full JSON payload shape for every API response — both
    success and failure. Fields map 1-to-1 to the lattice
    ``BaseResponse`` camelCase keys.

    Attributes:
        transaction_urn:  Unique per-request URN stamped on every response.
        reference_urn:    Optional domain-namespaced URN for sensitive mutations.
        status:           ``"SUCCESS"`` | ``"FAILURE"`` | ``"PENDING"``.
        response_message: Human-readable summary of the result.
        response_key:     Machine-readable result code (e.g. ``"USER_CREATED"``).
        errors:           Per-field validation errors; empty on success.
        timestamp:        ISO-8601 UTC timestamp.
        metadata:         Arbitrary key-value context (pagination, rate limits, etc.).
        data:             Actual response payload; ``None`` on failure.
    """

    transaction_urn: str
    status: str
    response_key: str
    response_message: str
    timestamp: str
    reference_urn: str = ""
    errors: list[ValidationErrorItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Return the camelCase response dict — JSON-safe."""
        formatted_errors = []
        for e in self.errors:
            if hasattr(e, "to_dict"):
                formatted_errors.append(e.to_dict())
            elif isinstance(e, dict):
                formatted_errors.append(e)
            else:
                formatted_errors.append(str(e))

        return {
            "transactionUrn": self.transaction_urn,
            "referenceUrn": self.reference_urn,
            "status": self.status,
            "responseMessage": self.response_message,
            "responseKey": self.response_key,
            "errors": formatted_errors,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "data": self.data,
        }

    def to_json(self) -> bytes:
        """Return UTF-8 JSON bytes of the response."""
        return serialize(self.to_dict())

    @classmethod
    def failed(
        cls,
        *,
        response_message: str,
        response_key: str,
        errors: list[ValidationErrorItem] | None = None,
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
        transaction_urn: str | None = None,
    ) -> Self:
        """Construct a failed response payload."""
        from rivex.utilities.response import ResponseUtility

        return cls(
            transaction_urn=transaction_urn or ResponseUtility.mint_urn(),
            reference_urn=reference_urn or "",
            status="FAILURE",
            response_key=response_key,
            response_message=response_message,
            errors=list(errors or []),
            timestamp=ResponseUtility.iso8601_now(),
            metadata=metadata or {},
            data=None,
        )

    @classmethod
    def success(
        cls,
        data: Any = None,
        *,
        response_message: str = "Operation completed successfully",
        response_key: str = "SUCCESS",
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
        transaction_urn: str | None = None,
    ) -> Self:
        """Construct a successful response payload."""
        from rivex.utilities.response import ResponseUtility

        return cls(
            transaction_urn=transaction_urn or ResponseUtility.mint_urn(),
            reference_urn=reference_urn or "",
            status="SUCCESS",
            response_key=response_key,
            response_message=response_message,
            errors=[],
            timestamp=ResponseUtility.iso8601_now(),
            metadata=metadata or {},
            data=data,
        )


def response_dto(
    data: Any = None,
    *,
    status_code: int = 200,
    response_key: str = "SUCCESS",
    message: str = "Operation completed successfully",
    errors: list[ValidationErrorItem] | None = None,
    reference_urn: str | None = None,
    metadata: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """Helper function to build a ResponseDTO wrapped in an HTTPResponse."""
    from rivex.dtos.response.content.http_response import HTTPResponse

    if status_code < 400:
        dto = ResponseDTO.success(
            data=data,
            response_message=message,
            response_key=response_key,
            reference_urn=reference_urn,
            metadata=metadata,
        )
    else:
        dto = ResponseDTO.failed(
            response_message=message,
            response_key=response_key,
            errors=errors,
            reference_urn=reference_urn,
            metadata=metadata,
        )
    return HTTPResponse(envelope=dto, status_code=status_code, headers=headers or {})


__all__ = ["IResponseDTO", "ResponseDTO", "response_dto"]
