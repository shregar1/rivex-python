"""``rivex.auth.abstraction`` — base authentication & authorization interface.

Provides ``IAuthProvider`` and ``IAuthGuard`` base interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IAuthProvider(ABC):
    """Base interface for authentication provider backends."""

    @abstractmethod
    async def authenticate(self, credentials: Any) -> Any:
        """Authenticate user credentials."""
        raise NotImplementedError


class IAuthGuard(ABC):
    """Base interface for route authorization guards."""

    @abstractmethod
    async def check_permissions(self, user: Any, required: list[str]) -> bool:
        """Check if authenticated user holds required permissions."""
        raise NotImplementedError


__all__ = ["IAuthProvider", "IAuthGuard"]
