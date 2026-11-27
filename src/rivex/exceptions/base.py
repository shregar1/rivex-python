"""Base foundation for Rivex HTTP exceptions.

Provides ``RivexException`` and ``ValidationErrorItem``.
Specific interface classes (e.g., ``INotFoundException``) live in their respective status files.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import Any

from rivex.constants import HTTPStatus
from rivex.exceptions.abstraction import IException


@dataclass
class ValidationErrorItem:
    """Per-field validation feedback (``errors`` array entry)."""

    field: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Serialize this validation item to a plain ``dict``.

        Returns:
            A dict with the ``field``, ``code``, and ``message`` keys
            preserved verbatim, suitable for inclusion in an
            ``errors`` array of a standard error envelope.
        """
        return {"field": self.field, "code": self.code, "message": self.message}


class RivexException(IException, ABC):
    """Base class for every framework-shaped exception."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    message: str = "Internal server error"
    errors: list[ValidationErrorItem] = []
    details: dict[str, Any] | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        errors: list[ValidationErrorItem] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if errors is not None:
            self.errors = list(errors)
        if details is not None:
            self.details = details
        Exception.__init__(self, self.message)

    def with_errors(self, errors: list[ValidationErrorItem]) -> RivexException:
        """Attach per-field validation errors and return ``self``.

        A defensive copy of the supplied list is stored so later
        mutations of the caller's list do not leak into the exception.

        Args:
            errors: Validation items to attach to this exception.

        Returns:
            This exception, so the call can be chained.
        """
        self.errors = list(errors)
        return self

    def with_details(self, details: dict[str, Any] | None) -> RivexException:
        """Attach an arbitrary details mapping and return ``self``.

        Args:
            details: Free-form metadata to embed in the rendered
                envelope, or ``None`` to clear any previous details.

        Returns:
            This exception, so the call can be chained.
        """
        self.details = details
        return self

    def to_response(self) -> dict[str, Any]:
        """Render this exception as the standard envelope dict."""
        from rivex.utilities.response import ResponseUtility

        return {
            "transactionUrn": ResponseUtility.mint_urn(),
            "referenceUrn": "",
            "status": "FAILURE",
            "responseMessage": self.message,
            "responseKey": self.code,
            "errors": [e.to_dict() for e in self.errors],
            "timestamp": ResponseUtility.iso8601_now(),
            "metadata": self.details or {},
            "data": None,
        }


__all__ = [
    "RivexException",
    "ValidationErrorItem",
]
