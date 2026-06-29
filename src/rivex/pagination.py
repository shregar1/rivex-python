from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class Page(Generic[T]):
    """A page of results with metadata."""

    items: Sequence[T]
    total: int
    page: int
    size: int

    @property
    def pages(self) -> int:
        if self.size <= 0:
            return 0
        return (self.total + self.size - 1) // self.size

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    def dict(self) -> dict[str, Any]:
        items = self.items
        if hasattr(items, "__iter__"):
            serialized = []
            for item in items:
                if hasattr(item, "model_dump"):
                    serialized.append(item.model_dump())
                elif hasattr(item, "__dict__"):
                    serialized.append(item.__dict__)
                else:
                    serialized.append(item)
            items = serialized
        return {
            "items": items,
            "total": self.total,
            "page": self.page,
            "size": self.size,
            "pages": self.pages,
            "has_next": self.has_next,
            "has_previous": self.has_previous,
        }


@dataclass
class CursorPage(Generic[T]):
    """Cursor-based pagination result."""

    items: Sequence[T]
    cursor: str | None
    has_more: bool

    def dict(self) -> dict[str, Any]:
        items = self.items
        if hasattr(items, "__iter__"):
            serialized = []
            for item in items:
                if hasattr(item, "model_dump"):
                    serialized.append(item.model_dump())
                elif hasattr(item, "__dict__"):
                    serialized.append(item.__dict__)
                else:
                    serialized.append(item)
            items = serialized
        return {
            "items": items,
            "cursor": self.cursor,
            "has_more": self.has_more,
        }


def paginate(
    items: Sequence[T], page: int = 1, size: int = 20, total: int | None = None
) -> Page[T]:
    """Create a Page from a full collection (offset-based)."""
    if total is None:
        total = len(items)
    start = (page - 1) * size
    end = start + size
    return Page(items=items[start:end], total=total, page=page, size=size)
