"""Service dependencies (Rivex DI targets)."""

from dependencies.services.item_service import (
    CreateItemServiceDependency,
    DeleteItemServiceDependency,
    GetItemServiceDependency,
    ListItemsServiceDependency,
    UpdateItemServiceDependency,
)

__all__ = [
    "CreateItemServiceDependency",
    "DeleteItemServiceDependency",
    "GetItemServiceDependency",
    "ListItemsServiceDependency",
    "UpdateItemServiceDependency",
]
