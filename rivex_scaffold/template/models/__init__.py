"""ORMX persistence models."""

from models.base import BaseModel
from models.item import Item

ALL_MODELS: tuple[type, ...] = (Item,)

__all__ = ["ALL_MODELS", "BaseModel", "Item"]
