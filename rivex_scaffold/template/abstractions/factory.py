"""Factory contract — object creation and wiring."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from abstractions.context import ContextMixin

T = TypeVar("T")


class IFactory(ContextMixin, ABC, Generic[T]):
    """Creates configured instances. Implementations live in ``factories/``."""

    @classmethod
    @abstractmethod
    def factory_name(cls) -> str:
        """Stable factory identifier."""

    @abstractmethod
    def create(self, **overrides: Any) -> T:
        """Build and return a fully wired instance."""

    def __init__(self, **kwargs: Any) -> None:
        ContextMixin.__init__(self, **kwargs)
