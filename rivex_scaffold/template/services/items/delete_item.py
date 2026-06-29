"""Soft-delete an item."""

from __future__ import annotations

from abstractions.service import IService
from constants.logger import ITEM_DELETED
from dtos.items import DeleteItemRequest, DeleteItemResponse
from errors import NotFoundError
from repositories.item import ItemRepository
from utilities.timing import timer


class DeleteItemService(IService[DeleteItemRequest, DeleteItemResponse]):
    """Mark an item as deleted (soft delete)."""

    def __init__(self, *, item_repo: ItemRepository | None = None) -> None:
        super().__init__()
        self._repo = item_repo or ItemRepository()

    @timer("service")
    async def run(self, request: DeleteItemRequest) -> DeleteItemResponse:
        deleted = await self._repo.delete(request.item_id)
        if not deleted:
            raise NotFoundError("item", str(request.item_id))
        self.logger.info("Item deleted", code=ITEM_DELETED, item_id=request.item_id)
        return DeleteItemResponse(item_id=request.item_id, deleted=True)
