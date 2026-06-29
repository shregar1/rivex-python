"""Request or domain validation failure."""

from __future__ import annotations

from typing import Any

from errors.domain_error import DomainError


class ValidationError(DomainError):
    code = "VALIDATION_ERROR"
    status_code = 422

    def __init__(
        self,
        message: str = "Validation failed",
        *,
        field: str | None = None,
        **context: Any,
    ) -> None:
        super().__init__(message, **context)
        self.field = field
