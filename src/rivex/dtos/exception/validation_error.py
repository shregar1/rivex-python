"""``rivex.dtos.exception.validation_error`` — per-field validation error DTO."""

from __future__ import annotations

from dataclasses import dataclass

from rivex.dtos.exception.abstraction import IExceptionDTO
from rivex.serialization.serialization import serialize


@dataclass
class ValidationErrorItem(IExceptionDTO):
    """Per-field validation feedback included in the ``errors`` array of every error envelope.

    Attributes:
        field:   The request field path that failed validation (e.g. ``"email"``).
        code:    Machine-readable error code (e.g. ``"REQUIRED"``).
        message: Human-readable explanation for the failure.

    Example::

        from rivex.dtos import ValidationErrorItem

        item = ValidationErrorItem(field="email", code="INVALID_FORMAT", message="Not a valid email")
        item.to_dict()  # {"field": "email", "code": "INVALID_FORMAT", "message": "Not a valid email"}
    """

    field: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "code": self.code, "message": self.message}

    def to_json(self) -> bytes:
        return serialize(self.to_dict())


__all__ = ["ValidationErrorItem"]
