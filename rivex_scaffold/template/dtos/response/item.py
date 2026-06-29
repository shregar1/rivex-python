"""Item response DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from rivex import Field

from dtos.base import ApplicationBaseModel


class ItemResponse(ApplicationBaseModel):
    """Single item payload returned by the API."""

    id: int
    urn: UUID
    title: str
    description: str
    is_completed: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateItemResponse(ApplicationBaseModel):
    """Returned from ``POST /items`` (subset of full representation)."""

    id: int
    urn: UUID
    title: str
    description: str


class GetItemResponse(ItemResponse):
    """Returned from ``GET /items/{id}``."""


class UpdateItemResponse(ItemResponse):
    """Returned from ``PATCH /items/{id}``."""


class DeleteItemResponse(ApplicationBaseModel):
    """Returned from ``DELETE /items/{id}``."""

    item_id: int
    deleted: bool = Field(default=True)


class ListItemsResponse(ApplicationBaseModel):
    """Paginated list of items."""

    items: list[ItemResponse]
    total: int
    offset: int
    limit: int


__all__ = [
    "ItemResponse",
    "CreateItemResponse",
    "GetItemResponse",
    "UpdateItemResponse",
    "DeleteItemResponse",
    "ListItemsResponse",
]
