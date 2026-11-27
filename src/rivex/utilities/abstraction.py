"""``rivex.utilities.abstraction`` — base utility interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class IUtility(ABC):
    """Base interface for framework utility components."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Returns the class name."""
        raise NotImplementedError


class LayeredUtility(IUtility):
    """Mixin base that handles the standard ``urn / tenant / user`` context bag.

    All app-level utilities in Rivex follow the same constructor shape
    so they can be instantiated with the same DI arguments; this base
    captures that boilerplate in one place.
    """

    def __init__(
        self,
        urn: Optional[str] = None,
        tenant_id: Optional[int] = None,
        tenant_urn: Optional[str] = None,
        user_id: Optional[int] = None,
        user_urn: Optional[str] = None,
        api_name: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        # Don't forward to object.__init__ — the *args/**kwargs are
        # silently dropped so subclasses don't have to declare the
        # standard context bag themselves.
        self.urn = urn
        self.tenant_id = tenant_id
        self.tenant_urn = tenant_urn
        self.user_id = user_id
        self.user_urn = user_urn
        self.api_name = api_name
        self.ip_address = ip_address
        self.user_agent = user_agent


__all__ = ["IUtility", "LayeredUtility"]

