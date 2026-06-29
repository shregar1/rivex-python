"""
MySQL adapter — requires ``aiomysql``.

This module is part of *rivex-adapter* and auto-registers the
``mysql://`` scheme when imported.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from rivex.db import DatabaseConfig, DatabasePool, register_driver


class AiomysqlPool(DatabasePool):
    """Connection pool for MySQL via ``aiomysql``."""

    def __init__(self, config: DatabaseConfig) -> None:
        super().__init__(config)
        self._pool: Any = None

    async def connect(self) -> None:
        import aiomysql

        parsed = urlparse(self.config.url)
        self._pool = await aiomysql.create_pool(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password or "",
            db=parsed.path.lstrip("/") if parsed.path else None,
            minsize=self.config.min_size,
            maxsize=self.config.max_size,
            echo=self.config.echo,
            **self.config.kwargs,
        )

    async def disconnect(self) -> None:
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
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
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in rows]

    async def execute(self, sql: str, params: tuple = ()) -> int:
        if self._pool is None:
            raise RuntimeError("Pool not connected")
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                await conn.commit()
                return cur.rowcount


register_driver("mysql", AiomysqlPool)
