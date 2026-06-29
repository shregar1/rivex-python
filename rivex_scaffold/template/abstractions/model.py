"""Persistence / domain model contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Self


class IModel(ABC):
    """Every persisted entity exposes identity and lifecycle metadata."""

    @property
    @abstractmethod
    def entity_id(self) -> str:
        """Primary identifier as a string (ORM ``id`` columns map here)."""

    @classmethod
    @abstractmethod
    def entity_type(cls) -> str:
        """Stable entity name for logs, audits, and OpenAPI tags."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize model fields for DTO mapping."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement to_dict()")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Hydrate from a plain dict."""
        raise NotImplementedError(f"{cls.__name__} must implement from_dict()")
