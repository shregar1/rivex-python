"""Item persistence model."""

from __future__ import annotations

from ormx import Field, StringField

from models.base import BaseModel


class Item(BaseModel):
    """Example entity. Copy and rename to add new resources."""

    __tablename__ = "items"

    title: str = StringField(max_length=200)
    description: str = StringField(max_length=2000, default="")
    is_completed: bool = Field(default=False)

    @classmethod
    def entity_type(cls) -> str:
        return "item"
