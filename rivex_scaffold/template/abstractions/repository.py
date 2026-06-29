"""Repository contract — async data access with shared ORM CRUD."""

from __future__ import annotations

import inspect
from abc import ABC
from typing import Any, ClassVar, Generic, Sequence, TypeVar
from uuid import UUID

from abstractions.context import ContextMixin
from utilities.timing import timer

TModel = TypeVar("TModel")
TId = TypeVar("TId", int, str)


class IRepository(ContextMixin, ABC, Generic[TModel, TId]):
    """Async persistence port. Subclasses set ``model_class``; CRUD is inherited.

    Public async methods are timed automatically. Inherited CRUD is already decorated.
    """

    model_class: ClassVar[type[Any] | None] = None
    soft_delete: ClassVar[bool] = True
    slow_query_ms: ClassVar[float] = 500.0

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls is IRepository:
            return
        if cls.model_class is None:
            raise TypeError(f"{cls.__name__} must define model_class")
        for name, attr in list(cls.__dict__.items()):
            if name.startswith("_"):
                continue
            if not inspect.iscoroutinefunction(attr):
                continue
            if getattr(attr, "__timer_layer__", None) is not None:
                continue
            setattr(cls, name, timer("repository", operation=name)(attr))

    @classmethod
    def _model(cls) -> type[TModel]:
        if cls.model_class is None:
            raise RuntimeError(f"{cls.__name__} must define model_class")
        return cls.model_class  # type: ignore[return-value]

    @classmethod
    def _supports_soft_delete(cls) -> bool:
        return cls.soft_delete and "is_deleted" in cls._model().model_fields

    @classmethod
    def _query(cls):
        query = cls._model().query()
        if cls._supports_soft_delete():
            query = query.where(cls._model().is_deleted == False)  # noqa: E712
        return query

    @timer("repository")
    async def find_by_id(self, entity_id: TId) -> TModel | None:
        entity = await self._model().get(entity_id)
        if entity is None:
            return None
        if self._supports_soft_delete() and entity.is_deleted:
            return None
        return entity

    async def find_by_urn(self, urn: UUID) -> TModel | None:
        if "urn" not in self._model().model_fields:
            return None
        return await self._find_by_urn(urn)

    @timer("repository", operation="find_by_urn")
    async def _find_by_urn(self, urn: UUID) -> TModel | None:
        return await self._query().where(self._model().urn == urn).first()

    @timer("repository")
    async def find_all(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[TModel]:
        return await self._query().offset(offset).limit(limit).all()

    @timer("repository")
    async def create(self, entity: TModel) -> TModel:
        return await entity.save()

    @timer("repository")
    async def update(self, entity: TModel) -> TModel:
        return await entity.save()

    @timer("repository")
    async def delete(self, entity_id: TId) -> bool:
        entity = await self._model().get(entity_id)
        if entity is None:
            return False
        if self._supports_soft_delete():
            entity.is_deleted = True
            await entity.save()
            return True
        await entity.delete()
        return True

    @timer("repository")
    async def count(self) -> int:
        return await self._query().count()
