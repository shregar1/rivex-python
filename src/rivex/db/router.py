from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any


class DatabaseRouter:
    """Route database operations to specific databases based on model.

    Usage::

        class MyRouter(DatabaseRouter):
            def db_for_read(self, model):
                return "replica" if model.__name__ == "LogEntry" else "default"

            def db_for_write(self, model):
                return "default"

        app.db.add_router(MyRouter())
    """

    def db_for_read(self, model: type | str) -> str | None:
        """Return the database alias to use for read operations."""
        return None

    def db_for_write(self, model: type | str) -> str | None:
        """Return the database alias to use for write operations."""
        return None

    def allow_migrate(self, model: type | str, db: str) -> bool | None:
        """Return True if the model should be migrated on the given database."""
        return None

    def allow_relation(self, model1: type | str, model2: type | str, db: str) -> bool | None:
        """Return True if a relation between model1 and model2 is allowed on db."""
        return None


class RouterRegistry:
    """Manages multiple database routers."""

    def __init__(self):
        self._routers: list[DatabaseRouter] = []

    def add(self, router: DatabaseRouter) -> None:
        """Register *router* in the registry.

        Args:
            router: The :class:`DatabaseRouter` instance to add. Routers
                are consulted in registration order.
        """
        self._routers.append(router)

    def remove(self, router: DatabaseRouter) -> None:
        """Remove a previously registered router.

        Args:
            router: The router instance to drop. Unknown routers are
                silently ignored.
        """
        if router in self._routers:
            self._routers.remove(router)

    def db_for_read(self, model: type | str) -> str | None:
        """Return the database alias the first router picks for reads.

        Args:
            model: Model class or its string name.

        Returns:
            The alias chosen by the first router that answers, or
            ``None`` if every router defers the decision.
        """
        for router in self._routers:
            result = router.db_for_read(model)
            if result is not None:
                return result
        return None

    def db_for_write(self, model: type | str) -> str | None:
        """Return the database alias the first router picks for writes.

        Args:
            model: Model class or its string name.

        Returns:
            The alias chosen by the first router that answers, or
            ``None`` if every router defers the decision.
        """
        for router in self._routers:
            result = router.db_for_write(model)
            if result is not None:
                return result
        return None

    def allow_migrate(self, model: type | str, db: str) -> bool:
        """Decide whether *model* is migratable on *db* by walking the routers.

        Args:
            model: Model class or its string name.
            db: Target database alias.

        Returns:
            The first non-``None`` answer from a registered router, or
            ``True`` as the permissive default when no router expresses
            an opinion.
        """
        for router in self._routers:
            result = router.allow_migrate(model, db)
            if result is not None:
                return result
        return True

    def allow_relation(self, model1: type | str, model2: type | str, db: str) -> bool:
        """Decide whether a relation between two models is allowed on *db*.

        Args:
            model1: First model in the relation.
            model2: Second model in the relation.
            db: Target database alias.

        Returns:
            The first non-``None`` answer from a registered router, or
            ``True`` when no router expresses an opinion.
        """
        for router in self._routers:
            result = router.allow_relation(model1, model2, db)
            if result is not None:
                return result
        return True


def using(db_alias: str) -> Callable:
    """Decorator to execute a route handler using a specific database.

    Usage::

        @using("replica")
        async def dashboard(request):
            ...
    """
    def decorator(func: Callable) -> Callable:
        """Wrap *func* so it runs with the captured *db_alias* in scope.

        Sets ``request.state._db_alias`` when the first positional
        argument looks like a request, and stamps ``wrapper._db_alias``
        on the wrapper itself for later introspection.

        Args:
            func: Async route handler to wrap.

        Returns:
            The wrapped coroutine function with the alias recorded as
            ``_db_alias`` on the wrapper object.
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            """Pin the request's db alias and forward the call to *func*."""
            request = None
            if args and hasattr(args[0], "state"):
                request = args[0]
            if request:
                request.state._db_alias = db_alias
            return await func(*args, **kwargs)
        wrapper._db_alias = db_alias
        return wrapper
    return decorator
