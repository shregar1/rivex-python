"""Create an item."""

from __future__ import annotations

from abstractions.service import IService
from constants.logger import ITEM_CREATED
from dtos.items import CreateItemRequest, CreateItemResponse
from models.item import Item
from repositories.item import ItemRepository
from utilities.timing import timer


class CreateItemService(IService[CreateItemRequest, CreateItemResponse]):
    """Persist a new item and return its representation."""

    def __init__(self, *, item_repo: ItemRepository | None = None) -> None:
        super().__init__()
        self._repo = item_repo or ItemRepository()

    @timer("service")
    async def run(self, request: CreateItemRequest) -> CreateItemResponse:
        entity = Item(
            title=request.title,
            description=request.description,
        )
        saved = await self._repo.create(entity)
        self.logger.info(
            "Item created",
            code=ITEM_CREATED,
            item_id=saved.id,
            urn=str(saved.urn),
        )
        return CreateItemResponse(
            id=saved.id or 0,
            urn=saved.urn,
            title=saved.title,
            description=saved.description,
        )
