from __future__ import annotations

from typing import Any


class ContentTypeRegistry:
    """Manages content type registrations for generic foreign keys.

    Mirrors Django's contenttypes framework: each model gets a
    ``(app_label, model)`` entry in a ``rivex_content_type`` table.

    Usage::

        registry = ContentTypeRegistry()
        registry.register("blog", "Post", {"id": int, "title": str})
        ct = registry.get("blog", "Post")
        obj = registry.get_object(ct.id, 42)
    """

    def __init__(self, pool=None):
        self._pool = pool
        self._content_types: dict[tuple[str, str], dict] = {}
        self._id_map: dict[int, dict] = {}
        self._next_id = 1

    def register(self, app_label: str, model: str, fields: dict | None = None) -> dict:
        key = (app_label, model.lower())
        if key in self._content_types:
            return self._content_types[key]
        ct = {
            "id": self._next_id,
            "app_label": app_label,
            "model": model.lower(),
            "fields": fields or {},
        }
        self._content_types[key] = ct
        self._id_map[self._next_id] = ct
        self._next_id += 1
        return ct

    def get(self, app_label: str, model: str) -> dict | None:
        return self._content_types.get((app_label, model.lower()))

    def get_by_id(self, ct_id: int) -> dict | None:
        return self._id_map.get(ct_id)

    def all(self) -> list[dict]:
        return list(self._id_map.values())

    def get_object(self, content_type_id: int, object_id: Any) -> Any | None:
        ct = self.get_by_id(content_type_id)
        if ct is None:
            return None
        table = f"{ct['app_label']}_{ct['model']}"
        if self._pool:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return self._pool.fetch(f"SELECT * FROM {table} WHERE id = $1", object_id)
                return None
            except Exception:
                pass
        return None

    async def create_table(self) -> None:
        if self._pool is None:
            return
        await self._pool.execute(
            "CREATE TABLE IF NOT EXISTS rivex_content_type ("
            "id SERIAL PRIMARY KEY,"
            "app_label VARCHAR(100) NOT NULL,"
            "model VARCHAR(100) NOT NULL,"
            "UNIQUE(app_label, model)"
            ")"
        )


class GenericForeignKey:
    """Descriptor for a generic foreign key field.

    Usage on a model::

        class Comment:
            content_type_id = int
            object_id = int
            content_object = GenericForeignKey("content_type_id", "object_id")
    """

    def __init__(self, ct_field: str = "content_type_id", fk_field: str = "object_id"):
        self._ct_field = ct_field
        self._fk_field = fk_field
        self._registry: ContentTypeRegistry | None = None

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        ct_id = getattr(instance, self._ct_field, None)
        obj_id = getattr(instance, self._fk_field, None)
        if ct_id is None or obj_id is None:
            return None
        if self._registry:
            return self._registry.get_object(ct_id, obj_id)
        return {"content_type_id": ct_id, "object_id": obj_id}

    def __set__(self, instance, value):
        if isinstance(value, dict):
            setattr(instance, self._ct_field, value.get("content_type_id"))
            setattr(instance, self._fk_field, value.get("object_id"))
        elif hasattr(value, "_content_type_id") and hasattr(value, "id"):
            setattr(instance, self._ct_field, value._content_type_id)
            setattr(instance, self._fk_field, value.id)


class GenericRelation:
    """Descriptor for reverse generic relation lookup."""

    def __init__(self, content_type_id: int, fk_field: str = "object_id"):
        self._content_type_id = content_type_id
        self._fk_field = fk_field
        self._pool = None

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        obj_id = getattr(instance, "id", None)
        if obj_id is None:
            return []
        table = owner.__name__.lower()
        if self._pool:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return self._pool.fetch(
                        f"SELECT * FROM {table} "
                        f"WHERE content_type_id = $1 AND {self._fk_field} = $2",
                        self._content_type_id, obj_id
                    )
            except Exception:
                pass
        return []


# Global registry
_registry = ContentTypeRegistry()


def get_content_type(model_cls: type) -> dict | None:
    """Get or create a content type entry for a model class.

    Inspects ``model_cls.__app_label__`` and ``model_cls.__name__``.
    """
    app_label = getattr(model_cls, "__app_label__", "default")
    model_name = model_cls.__name__.lower()
    return _registry.register(app_label, model_name, getattr(model_cls, "__columns__", None))


def get_object(content_type_id: int, object_id: Any) -> Any | None:
    return _registry.get_object(content_type_id, object_id)
