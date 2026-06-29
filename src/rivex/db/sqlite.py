"""
SQLite adapter — uses ``aiosqlite`` from stdlib.

Import this module to register the ``sqlite://`` scheme::

    import rivex.db.sqlite  # noqa: F401
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from rivex.db import DatabaseConfig, DatabasePool, register_driver


class SqlitePool(DatabasePool):
    """Connection pool for SQLite via ``aiosqlite``."""

    def __init__(self, config: DatabaseConfig) -> None:
        super().__init__(config)
        self._conn: Any = None

    async def connect(self) -> None:
        import aiosqlite

        path = re.sub(r"^sqlite:///", "", self.config.url)
        self._conn = await aiosqlite.connect(path)
        self._conn.row_factory = aiosqlite.Row

    async def disconnect(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        if self._conn is None:
            raise RuntimeError("Pool not connected")
        try:
            yield self._conn
        except BaseException:
            await self._conn.rollback()
            raise
        else:
            await self._conn.commit()

    async def fetch(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        cur = await self._conn.execute(sql, params)
        rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def execute(self, sql: str, params: tuple = ()) -> int:
        cur = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cur.rowcount


register_driver("sqlite", SqlitePool)
