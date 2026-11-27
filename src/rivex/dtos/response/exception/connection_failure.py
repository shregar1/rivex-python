"""Connection failure domain exception response DTO."""

from __future__ import annotations

from typing import Any, Self

from rivex.dtos.exception import ValidationErrorItem
from rivex.dtos.response.exception.abstraction import IExceptionResponseDTO
from rivex.exceptions.domain.connection_failure import ConnectionFailureException


class ConnectionFailureExceptionResponse(IExceptionResponseDTO):
    """Specialized response DTO for ConnectionFailureException cases."""

    @classmethod
    def from_connection_failure_exception(
        cls,
        err: ConnectionFailureException,
        *,
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """Construct a connection failure error response from a ConnectionFailureException instance."""
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
        return cls.from_connection_failure_exception(err, reference_urn=reference_urn, metadata=metadata)


__all__ = ["ConnectionFailureExceptionResponse"]
