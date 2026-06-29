"""
PostgreSQL adapter — requires ``asyncpg``.

This module is part of *rivex-adapter* and auto-registers the
``postgresql://`` scheme when imported.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from rivex.db import DatabaseConfig, DatabasePool, register_driver


class AsyncpgPool(DatabasePool):
    """Connection pool for PostgreSQL via ``asyncpg``."""

    def __init__(self, config: DatabaseConfig) -> None:
        super().__init__(config)
        self._pool: Any = None

    async def connect(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(
            dsn=self.config.url,
            min_size=self.config.min_size,
            max_size=self.config.max_size,
            timeout=self.config.pool_timeout,
        )

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        if self._pool is None:
            raise RuntimeError("Pool not connected")
        async with self._pool.acquire() as conn:
            yield conn

    async def fetch(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        if self._pool is None:
            raise RuntimeError("Pool not connected")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [dict(row) for row in rows]

    async def execute(self, sql: str, params: tuple = ()) -> str:
        if self._pool is None:
            raise RuntimeError("Pool not connected")
        async with self._pool.acquire() as conn:
            return await conn.execute(sql, *params)


register_driver("postgresql", AsyncpgPool)
register_driver("postgres", AsyncpgPool)
