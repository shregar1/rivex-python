"""Authenticated but not permitted."""

from __future__ import annotations

from typing import Any

from errors.domain_error import DomainError


class ForbiddenError(DomainError):
    code = "FORBIDDEN"
    status_code = 403

    def __init__(self, message: str = "Forbidden", **context: Any) -> None:
        super().__init__(message, **context)
