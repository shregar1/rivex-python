from __future__ import annotations

from typing import Any

from abstractions.error import IError


class DomainError(IError):
    """Base application error with HTTP mapping."""

    code: str = "DOMAIN_ERROR"
    status_code: int = 400

    def __init__(self, message: str = "Domain error", **context: Any) -> None:
        super().__init__(message, code=self.code, status_code=self.status_code, **context)
