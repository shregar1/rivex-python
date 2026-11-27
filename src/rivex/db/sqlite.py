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
        """Open the underlying ``aiosqlite`` connection for this pool.

        Strips the ``sqlite://`` scheme from :attr:`config.url` to obtain
        the on-disk path, then opens the connection and configures row
        factory access on the resulting object.
        """
        import aiosqlite

        path = re.sub(r"^sqlite:///", "", self.config.url)
        self._conn = await aiosqlite.connect(path)
        self._conn.row_factory = aiosqlite.Row

    async def disconnect(self) -> None:
        """Close the underlying SQLite connection if one is open."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        """Yield the shared connection as a transactional context manager.

        On a clean exit the implicit transaction is committed; any
        exception escaping the block triggers a rollback before
        re-raising so the connection is left in a consistent state.

        Raises:
            RuntimeError: If :meth:`connect` has not been awaited yet.

        Yields:
            The shared ``aiosqlite`` connection.
        """
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
        """Run *sql* and return every row as a ``dict``.

        Args:
            sql: Parameterized SQL statement to execute.
            params: Positional parameters bound to the statement.

        Returns:
            A list of plain ``dict`` objects with column names as keys.
        """
        cur = await self._conn.execute(sql, params)
        rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def execute(self, sql: str, params: tuple = ()) -> int:
        """Run a write statement and commit the transaction.

        Args:
            sql: Parameterized SQL statement to execute.
            params: Positional parameters bound to the statement.

        Returns:
            The number of rows affected as reported by the SQLite
            cursor.
        """
        cur = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cur.rowcount


register_driver("sqlite", SqlitePool)
