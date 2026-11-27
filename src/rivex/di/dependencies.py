"""Rivex dependency injection primitives.

The framework resolves ``Dependency`` markers in handler signatures before
calling the handler. Each ``Dependency`` either wraps a plain callable
(legacy marker form) or is subclassed to provide a ``resolve()`` method that
returns a service / context object.

Examples::

    # Marker form — wrap a callable
    async def get_db():
        return await connect()

    @app.get("/items")
    async def list_items(db=Dependency(get_db)):
        return await db.execute("SELECT 1")

    # Class form — subclass and implement resolve()
    class CurrentUser(Dependency):
        def resolve(self, request):
            return request.state.user

    @app.get("/me")
    async def me(user=Dependency(CurrentUser())):
        return user

Caching and scope can be tuned per ``Dependency`` instance::

    Dependency(get_db, use_cache=False)            # recompute every request
    Dependency(get_settings, scope="singleton")    # share across the process

Caching behaviour:

* ``use_cache=True`` (default) — the resolved value is cached per-request so
  the same callable only runs once even if referenced by multiple parameters.
* ``use_cache=False`` — the callable runs every time the parameter is resolved.
* ``scope="request"`` (default) — cache lives for the duration of one request.
* ``scope="singleton"`` — cache lives for the process lifetime.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Dependency:
    """Marker / base class for a dependency that the framework resolves before calling a handler.

    Use it in one of two ways:

    1. **Marker** — pass a callable to the constructor. The framework will
       instantiate a class callable (passing no arguments) or call a function /
       async function as appropriate::

           Dependency(get_user)        # function / async function
           Dependency(SomeClass)       # class — instantiated with no args

    2. **Subclass** — extend :class:`Dependency` and implement ``resolve()``::

           class MyService(Dependency):
               def resolve(self):
                   return MyServiceImpl()

           Dependency(MyService())

    The second form lets you put request-scoped state (e.g. from a context
    mixin) on the dependency instance and have the framework call ``resolve``
    on it.

    Args:
        dependency: Callable, class, or ``None`` when subclassing. Stored as
            ``self.dependency``; the framework reads it to find the callable
            to invoke.
        use_cache: When ``True`` (default), the resolved value is reused
            across multiple parameters in the same request. Set ``False``
            to force re-resolution on every access.
        scope: ``"request"`` (default) caches for the lifetime of a single
            request; ``"singleton"`` caches for the process lifetime.
    """

    __slots__ = ("dependency", "use_cache", "scope")

    def __init__(
        self,
        dependency: Callable[..., Any] | type | None = None,
        *,
        use_cache: bool = True,
        scope: str = "request",
    ):
        self.dependency = dependency
        self.use_cache = use_cache
        self.scope = scope

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Legacy invocation path — delegates to :meth:`resolve` and awaits the result if awaitable."""
        result = self.resolve(*args, **kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result

    def resolve(self, *args: Any, **kwargs: Any) -> Any:
        """Return the value to inject.

        Subclasses override this method. The default implementation raises
        :class:`NotImplementedError`, signalling that the class was used as a
        marker (in which case the framework ignores ``resolve`` and invokes
        the callable in :attr:`dependency` instead).
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        """Compact representation showing the wrapped dependency name."""
        attr = getattr(self.dependency, "__name__", repr(self.dependency))
        return f"Dependency({attr})"

class Depends(Dependency):
    pass
