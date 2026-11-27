"""Unauthorized exception response envelope DTO."""

from __future__ import annotations

from typing import Any, Self

from rivex.dtos.exception import ValidationErrorItem
from rivex.dtos.response.exception.abstraction import IExceptionResponseDTO
from rivex.exceptions.http.unauthorized import UnauthorizedException


class UnauthorizedExceptionResponse(IExceptionResponseDTO):
    """Specialized envelope response DTO for UnauthorizedException cases."""

    @classmethod
    def from_unauthorized_exception(
        cls,
        err: UnauthorizedException,
        *,
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """Construct an unauthorized error envelope response from an UnauthorizedException instance."""
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
        return cls.from_unauthorized_exception(err, reference_urn=reference_urn, metadata=metadata)


__all__ = ["UnauthorizedExceptionResponse"]
