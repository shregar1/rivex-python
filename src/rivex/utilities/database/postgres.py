"""Postgres utility — asyncpg connection pool and query helpers.

The ``asyncpg`` package is imported lazily inside :meth:`connect`.
When it isn't installed the utility stays in a disconnected state so
:func:`fetch` returns ``[]`` and :func:`execute` returns ``"SKIPPED"``.
"""

from __future__ import annotations

from typing import Any, List, Optional

from rivex.utilities.abstraction import LayeredUtility
from rivex.utilities.database.abstraction import IDatabaseUtility


class PostgresDatabaseUtility(IDatabaseUtility, LayeredUtility):
    """Thin wrapper around an asyncpg pool with safe lifecycle helpers."""

    def __init__(
        self,
        connection_uri: str,
        pool_min_size: int = 1,
        pool_max_size: int = 10,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.connection_uri = connection_uri
        self.pool_min_size = int(pool_min_size)
        self.pool_max_size = int(pool_max_size)
        self._pool: Any = None

    async def connect(self) -> Any:
        """Open an asyncpg connection pool and return it."""
        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self.connection_uri,
                min_size=self.pool_min_size,
                max_size=self.pool_max_size,
            )
            return self._pool
        except ImportError:
            self._pool = None
            return None

    async def disconnect(self) -> None:
        """Close the underlying asyncpg pool."""
        if self._pool is not None and hasattr(self._pool, "close"):
            await self._pool.close()
        self._pool = None

    async def fetch(self, query: str, *args: Any) -> List[Any]:
        """Run a SELECT and return all rows (``[]`` when disconnected)."""
        if self._pool is None:
            return []
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        """Run a write query and return its status string (``"SKIPPED"`` when disconnected)."""
        if self._pool is None:
            return "SKIPPED"
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    @property
    def pool(self) -> Any:
        return self._pool

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "PostgresDatabaseUtility"


__all__ = ["PostgresDatabaseUtility"]
