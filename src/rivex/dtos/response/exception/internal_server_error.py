"""Internal server error exception response envelope DTO."""

from __future__ import annotations

from typing import Any, Self

from rivex.dtos.exception import ValidationErrorItem
from rivex.dtos.response.exception.abstraction import IExceptionResponseDTO
from rivex.exceptions.http.internal_server_error import InternalServerException


class InternalServerExceptionResponse(IExceptionResponseDTO):
    """Specialized envelope response DTO for InternalServerException cases."""

    @classmethod
    def from_internal_server_exception(
        cls,
        err: InternalServerException,
        *,
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """Construct an internal server error envelope response from an InternalServerException instance."""
        errors = [
            ValidationErrorItem(field=e.get("field", ""), code=e.get("code", err.code), message=e.get("message", err.message))
            if isinstance(e, dict)
            else e
            for e in getattr(err, "errors", [])
        ]
        return cls.failed(
            response_message=err.message,
            response_key=err.code,
            errors=errors,
            reference_urn=reference_urn,
            metadata=metadata or getattr(err, "details", None),
        )

    @classmethod
    def from_exception(
        cls,
        err: Any,
        *,
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        return cls.from_internal_server_exception(err, reference_urn=reference_urn, metadata=metadata)


__all__ = ["InternalServerExceptionResponse"]
