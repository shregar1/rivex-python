"""URN parsing for public routes."""

from __future__ import annotations

from uuid import UUID

from errors import NotFoundError

_RESERVED_URNS = frozenset({"me"})


def parse_public_urn(value: str, *, entity: str) -> UUID:
    if value in _RESERVED_URNS:
        raise NotFoundError(entity, value)
    try:
        return UUID(value)
    except ValueError:
        raise NotFoundError(entity, value) from None
