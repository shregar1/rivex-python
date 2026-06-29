"""Item repository."""

from __future__ import annotations

from models.item import Item

from abstractions.repository import IRepository


class ItemRepository(IRepository[Item, int]):
    """Inherits async CRUD from ``IRepository`` (find_by_id, find_all, create, update, delete, count)."""

    model_class = Item
    soft_delete = True
