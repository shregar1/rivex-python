"""Generic Rivex exception response envelope DTO."""

from __future__ import annotations

from typing import Any, Self

from rivex.dtos.exception import ValidationErrorItem
from rivex.dtos.response.exception.abstraction import IExceptionResponseDTO
from rivex.exceptions.base import RivexException


class RivexExceptionResponse(IExceptionResponseDTO):
    """Generic envelope response DTO for RivexException cases."""

    @classmethod
    def from_rivex_exception(
        cls,
        err: RivexException,
        *,
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """Construct a generic Rivex error envelope response from a RivexException instance."""
        errors = [
            ValidationErrorItem(field=e.get("field", ""), code=e.get("code", getattr(err, "code", "ERROR")), message=e.get("message", getattr(err, "message", str(err))))
            if isinstance(e, dict)
            else e
            for e in getattr(err, "errors", [])
        ]
        return cls.failed(
            response_message=getattr(err, "message", str(err)),
            response_key=getattr(err, "code", "INTERNAL_ERROR"),
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
        return cls.from_rivex_exception(err, reference_urn=reference_urn, metadata=metadata)


__all__ = ["RivexExceptionResponse"]
