"""``rivex.testing.abstraction`` — base testing client interface.

Provides ``ITestClient`` base interface for HTTP and ASGI test clients.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ITestClient(ABC):
    """Base interface for Rivex application test clients."""

    @abstractmethod
    def get(self, url: str, **kwargs: Any) -> Any:
        """Issue HTTP GET request."""
        raise NotImplementedError

    @abstractmethod
    def post(self, url: str, **kwargs: Any) -> Any:
        """Issue HTTP POST request."""
        raise NotImplementedError


__all__ = ["ITestClient"]
