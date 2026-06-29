"""{{model_class}} repository."""

from __future__ import annotations

from models.{{resource}} import {{model_class}}

from abstractions.repository import IRepository


class {{model_class}}Repository(IRepository[{{model_class}}, int]):
    """Inherits async CRUD from ``IRepository`` (find_by_id, find_all, create, update, delete, count)."""

    model_class = {{model_class}}
    soft_delete = True
