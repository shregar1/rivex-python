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
        self._routers.append(router)

    def remove(self, router: DatabaseRouter) -> None:
        if router in self._routers:
            self._routers.remove(router)

    def db_for_read(self, model: type | str) -> str | None:
        for router in self._routers:
            result = router.db_for_read(model)
            if result is not None:
                return result
        return None

    def db_for_write(self, model: type | str) -> str | None:
        for router in self._routers:
            result = router.db_for_write(model)
            if result is not None:
                return result
        return None

    def allow_migrate(self, model: type | str, db: str) -> bool:
        for router in self._routers:
            result = router.allow_migrate(model, db)
            if result is not None:
                return result
        return True

    def allow_relation(self, model1: type | str, model2: type | str, db: str) -> bool:
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
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = None
            if args and hasattr(args[0], "state"):
                request = args[0]
            if request:
                request.state._db_alias = db_alias
            return await func(*args, **kwargs)
        wrapper._db_alias = db_alias
        return wrapper
    return decorator
