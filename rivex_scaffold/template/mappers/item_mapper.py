"""ORM ↔ DTO mapping for the items slice."""

from __future__ import annotations

from models.item import Item

from dtos.response.item import ItemResponse


def item_to_response(item: Item) -> ItemResponse:
    return ItemResponse(
        id=item.id,
        urn=item.urn,
        title=item.title,
        description=item.description,
        is_completed=item.is_completed,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def items_to_response(items: list[Item]) -> list[ItemResponse]:
    return [item_to_response(item) for item in items]


__all__ = ["item_to_response", "items_to_response"]
