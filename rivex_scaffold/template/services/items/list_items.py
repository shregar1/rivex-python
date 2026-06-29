"""List items with pagination."""

from __future__ import annotations

from abstractions.service import IService
from constants.logger import ITEMS_LISTED
from dtos.items import ListItemsRequest, ListItemsResponse
from mappers import item_to_response
from repositories.item import ItemRepository
from utilities.timing import timer


class ListItemsService(IService[ListItemsRequest, ListItemsResponse]):
    """Paginated list of items."""

    def __init__(self, *, item_repo: ItemRepository | None = None) -> None:
        super().__init__()
        self._repo = item_repo or ItemRepository()

    @timer("service")
    async def run(self, request: ListItemsRequest) -> ListItemsResponse:
        items = await self._repo.find_all(offset=request.offset, limit=request.limit)
        total = await self._repo.count()
        self.logger.info("Items listed", code=ITEMS_LISTED, count=len(items), total=total)
        return ListItemsResponse(
            items=[item_to_response(item) for item in items],
            total=total,
            offset=request.offset,
            limit=request.limit,
        )
