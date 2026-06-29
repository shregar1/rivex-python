"""Service-layer Rivex DI bindings (example: items)."""

from __future__ import annotations

from typing import Any

from abstractions.dependency import IDependency
from services.items import (
    CreateItemService,
    DeleteItemService,
    GetItemService,
    ListItemsService,
    UpdateItemService,
)


class CreateItemServiceDependency(IDependency):
    def resolve(self, *args: Any, **kwargs: Any) -> CreateItemService:
        return CreateItemService()


class GetItemServiceDependency(IDependency):
    def resolve(self, *args: Any, **kwargs: Any) -> GetItemService:
        return GetItemService()


class ListItemsServiceDependency(IDependency):
    def resolve(self, *args: Any, **kwargs: Any) -> ListItemsService:
        return ListItemsService()


class UpdateItemServiceDependency(IDependency):
    def resolve(self, *args: Any, **kwargs: Any) -> UpdateItemService:
        return UpdateItemService()


class DeleteItemServiceDependency(IDependency):
    def resolve(self, *args: Any, **kwargs: Any) -> DeleteItemService:
        return DeleteItemService()
