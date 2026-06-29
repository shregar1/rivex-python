"""
Redis adapter — requires ``redis``.

This module is part of *rivex-adapter* and auto-registers the
``redis://`` scheme when imported.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from rivex.db import DatabaseConfig, DatabasePool, register_driver


class RedisPool(DatabasePool):
    """Connection pool for Redis via ``redis.asyncio``."""

    def __init__(self, config: DatabaseConfig) -> None:
        super().__init__(config)
        self._pool: Any = None

    async def connect(self) -> None:
        from redis.asyncio import ConnectionPool as RedisConnPool

        self._pool = RedisConnPool.from_url(
            self.config.url,
            max_connections=self.config.max_size,
            timeout=self.config.pool_timeout,
        )

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        if self._pool is None:
            raise RuntimeError("Pool not connected")
        from redis.asyncio import Redis

        async with Redis(connection_pool=self._pool) as conn:
            yield conn

    async def fetch(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        raise NotImplementedError("Redis does not support SQL fetch")

    async def execute(self, sql: str, params: tuple = ()) -> int:
        raise NotImplementedError("Redis does not support SQL execute")


register_driver("redis", RedisPool)
