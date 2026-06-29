"""Resource not found."""

from __future__ import annotations

from typing import Any

from errors.domain_error import DomainError


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    status_code = 404

    def __init__(self, resource: str, entity_id: str | None = None, **context: Any) -> None:
        detail = f"{resource} not found" if entity_id is None else f"{resource} '{entity_id}' not found"
        super().__init__(detail, **context)
        self.resource = resource
        self.entity_id = entity_id
