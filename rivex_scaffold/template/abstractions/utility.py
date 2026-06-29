"""Utility contract — stateless or singleton helpers."""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any

from abstractions.context import ContextMixin
from utilities.timing import timer


class IUtility(ContextMixin, ABC):
    """Cross-cutting helper. Implementations live in ``utilities/``."""

    @classmethod
    @abstractmethod
    def name(cls) -> str:
        """Stable utility identifier for logs and DI."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls is IUtility:
            return
        for name, attr in list(cls.__dict__.items()):
            if name.startswith("_"):
                continue
            if name == "name":
                continue
            if not inspect.iscoroutinefunction(attr):
                continue
            if getattr(attr, "__timer_layer__", None) is not None:
                continue
            setattr(cls, name, timer("utility", operation=name)(attr))

    def __init__(self, **kwargs: Any) -> None:
        ContextMixin.__init__(self, **kwargs)
