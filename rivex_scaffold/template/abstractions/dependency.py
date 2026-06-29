"""Rivex dependency injection contract."""

from __future__ import annotations

from abc import ABC
from typing import Any

from rivex import Dependency

from abstractions.context import ContextMixin


class IDependency(Dependency, ContextMixin, ABC):
    """Injectable request-scoped resource. Implementations live in ``dependencies/``."""

    def __init__(self, **kwargs: Any) -> None:
        ContextMixin.__init__(self, **kwargs)

    def resolve(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(f"{self.__class__.__name__} must implement resolve()")
