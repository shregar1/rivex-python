"""``rivex.middleware.abstraction`` — base middleware interface.

Provides ``IMiddleware``, the base interface protocol for all Rivex middleware modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class IMiddleware(ABC):
    """Base interface protocol for Rivex ASGI middleware components."""

    @abstractmethod
    async def process(self, request_data: dict[str, Any], call_next: Callable) -> dict[str, Any]:
        """Process an incoming request dictionary and pass control to the next handler."""
        raise NotImplementedError


Middleware = IMiddleware

__all__ = ["IMiddleware", "Middleware"]
