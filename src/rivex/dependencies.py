from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Dependency:
    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        result = self.resolve(*args, **kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result

    def resolve(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


class Depends:
    __slots__ = ("dependency", "use_cache", "scope")

    def __init__(
        self,
        dependency: Callable[..., Any] | type,
        *,
        use_cache: bool = True,
        scope: str = "request",
    ):
        self.dependency = dependency
        self.use_cache = use_cache
        self.scope = scope

    def __repr__(self) -> str:
        attr = getattr(self.dependency, "__name__", repr(self.dependency))
        return f"Depends({attr})"
