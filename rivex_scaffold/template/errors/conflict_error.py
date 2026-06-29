"""Conflict — duplicate or stale resource."""

from __future__ import annotations

from typing import Any

from errors.domain_error import DomainError


class ConflictError(DomainError):
    code = "CONFLICT"
    status_code = 409

    def __init__(self, message: str = "Conflict", **context: Any) -> None:
        super().__init__(message, **context)
