"""Item request DTOs."""

from __future__ import annotations

from rivex import Field

from dtos.requests import IRequestDto


class CreateItemRequest(IRequestDto):
    """Payload for ``POST /items``."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class GetItemRequest(IRequestDto):
    """Path params for ``GET /items/{id}``."""

    item_id: int = Field(ge=1)


class UpdateItemRequest(IRequestDto):
    """Payload for ``PATCH /items/{id}``. All fields optional for partial updates."""

    item_id: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_completed: bool | None = Field(default=None)


class DeleteItemRequest(IRequestDto):
    """Path params for ``DELETE /items/{id}``."""

    item_id: int = Field(ge=1)


class ListItemsRequest(IRequestDto):
    """Query params for ``GET /items``."""

    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)
    only_open: bool = Field(default=False)


__all__ = [
    "CreateItemRequest",
    "GetItemRequest",
    "UpdateItemRequest",
    "DeleteItemRequest",
    "ListItemsRequest",
]
