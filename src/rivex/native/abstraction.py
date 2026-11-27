"""``rivex.native.abstraction`` — base core framework interface.

Provides ``ICoreApplication`` and ``ICoreRouter`` base interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ICoreApplication(ABC):
    """Base interface for the main Rivex ASGI Application engine."""

    @abstractmethod
    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """ASGI 3.0 entrypoint callable interface."""
        raise NotImplementedError


class ICoreRouter(ABC):
    """Base interface for the Rivex core request router."""

    @abstractmethod
    def add_route(self, path: str, endpoint: Any, methods: list[str] | None = None) -> None:
        """Register a route path and endpoint handler."""
        raise NotImplementedError


__all__ = ["ICoreApplication", "ICoreRouter"]
