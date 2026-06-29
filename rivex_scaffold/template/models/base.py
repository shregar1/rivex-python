"""Shared ORMX base model implementing ``IModel``."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self
from uuid import UUID, uuid4

from ormx import Field, Model, UUIDField

from abstractions.model import IModel


class BaseModel(Model, IModel):
    """Base for all persistence models."""

    id: int | None = Field(default=None, primary_key=True)
    urn: UUID = UUIDField(unique=True, default_factory=uuid4)
    created_at: datetime | None = Field(default=None, server_default="now()")
    updated_at: datetime | None = Field(default=None, server_default="now()")
    is_deleted: bool = Field(default=False)

    @property
    def entity_id(self) -> str:
        return str(self.id)

    @classmethod
    def entity_type(cls) -> str:
        return cls.__tablename__

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls.model_validate(data)
