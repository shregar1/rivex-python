"""Fetch a single item by id."""

from __future__ import annotations

from abstractions.service import IService
from constants.logger import ITEM_FETCHED
from dtos.items import GetItemRequest, GetItemResponse
from errors import NotFoundError
from repositories.item import ItemRepository
from utilities.timing import timer


class GetItemService(IService[GetItemRequest, GetItemResponse]):
    """Return a single item or raise ``NotFoundError``."""

    def __init__(self, *, item_repo: ItemRepository | None = None) -> None:
        super().__init__()
        self._repo = item_repo or ItemRepository()

    @timer("service")
    async def run(self, request: GetItemRequest) -> GetItemResponse:
        item = await self._repo.find_by_id(request.item_id)
        if item is None:
            raise NotFoundError("item", str(request.item_id))
        self.logger.info("Item fetched", code=ITEM_FETCHED, item_id=item.id)
        return GetItemResponse(
            id=item.id or 0,
            urn=item.urn,
            title=item.title,
            description=item.description,
            is_completed=item.is_completed,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
