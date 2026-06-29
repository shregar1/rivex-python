"""Update an item."""

from __future__ import annotations

from abstractions.service import IService
from constants.logger import ITEM_UPDATED
from dtos.items import UpdateItemRequest, UpdateItemResponse
from errors import NotFoundError
from repositories.item import ItemRepository
from utilities.timing import timer


class UpdateItemService(IService[UpdateItemRequest, UpdateItemResponse]):
    """Apply a partial update to an item."""

    def __init__(self, *, item_repo: ItemRepository | None = None) -> None:
        super().__init__()
        self._repo = item_repo or ItemRepository()

    @timer("service")
    async def run(self, request: UpdateItemRequest) -> UpdateItemResponse:
        item = await self._repo.find_by_id(request.item_id)
        if item is None:
            raise NotFoundError("item", str(request.item_id))

        if request.title is not None:
            item.title = request.title
        if request.description is not None:
            item.description = request.description
        if request.is_completed is not None:
            item.is_completed = request.is_completed

        saved = await self._repo.update(item)
        self.logger.info("Item updated", code=ITEM_UPDATED, item_id=saved.id)
        return UpdateItemResponse(
            id=saved.id or 0,
            urn=saved.urn,
            title=saved.title,
            description=saved.description,
            is_completed=saved.is_completed,
            created_at=saved.created_at,
            updated_at=saved.updated_at,
        )
