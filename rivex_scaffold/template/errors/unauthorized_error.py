"""Authentication required."""

from __future__ import annotations

from typing import Any

from errors.domain_error import DomainError


class UnauthorizedError(DomainError):
    code = "UNAUTHORIZED"
    status_code = 401

    def __init__(self, message: str = "Unauthorized", **context: Any) -> None:
        super().__init__(message, **context)
