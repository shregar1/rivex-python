"""Items REST controller (example slice)."""

from __future__ import annotations

from rivex import Body, Path, Query, delete, get, patch, post

from abstractions.controller import IController
from constants.api import API_PREFIX, ITEMS_TAG
from dtos.items import (
    CreateItemRequest,
    DeleteItemRequest,
    GetItemRequest,
    ListItemsRequest,
    UpdateItemRequest,
)
from services.items import (
    CreateItemService,
    DeleteItemService,
    GetItemService,
    ListItemsService,
    UpdateItemService,
)
from utilities.timing import timer


class ItemsController(IController):
    """CRUD endpoints for the example ``items`` resource."""

    path = f"{API_PREFIX}/items"
    tags = [ITEMS_TAG]

    @classmethod
    def base_path(cls) -> str:
        return cls.path

    @get("", summary="List items")
    @timer("controller")
    async def list_items(
        self,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict:
        request = ListItemsRequest(offset=offset, limit=limit)
        service = ListItemsService()
        return await self.invoke_service(service, request)

    @get("/{item_id}", summary="Fetch an item")
    @timer("controller")
    async def get_item(self, item_id: int = Path(ge=1)) -> dict:
        request = GetItemRequest(item_id=item_id)
        service = GetItemService()
        return await self.invoke_service(service, request)

    @post("", summary="Create an item")
    @timer("controller")
    async def create_item(self, payload: CreateItemRequest = Body()) -> dict:
        service = CreateItemService()
        return await self.invoke_service(service, payload)

    @patch("/{item_id}", summary="Update an item")
    @timer("controller")
    async def update_item(
        self,
        item_id: int = Path(ge=1),
        payload: UpdateItemRequest = Body(),
    ) -> dict:
        request = UpdateItemRequest(
            item_id=item_id,
            title=payload.title,
            description=payload.description,
            is_completed=payload.is_completed,
        )
        service = UpdateItemService()
        return await self.invoke_service(service, request)

    @delete("/{item_id}", summary="Delete an item")
    @timer("controller")
    async def delete_item(self, item_id: int = Path(ge=1)) -> dict:
        request = DeleteItemRequest(item_id=item_id)
        service = DeleteItemService()
        return await self.invoke_service(service, request)
