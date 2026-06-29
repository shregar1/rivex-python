"""
MongoDB adapter — requires ``motor``.

This module is part of *rivex-adapter* and auto-registers the
``mongodb://`` scheme when imported.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from rivex.db import DatabaseConfig, DatabasePool, register_driver


class MotorPool(DatabasePool):
    """Connection pool for MongoDB via ``motor``."""

    def __init__(self, config: DatabaseConfig) -> None:
        super().__init__(config)
        self._client: Any = None

    async def connect(self) -> None:
        from motor.motor_asyncio import AsyncIOMotorClient

        self._client = AsyncIOMotorClient(
            self.config.url,
            maxPoolSize=self.config.max_size,
            serverSelectionTimeoutMS=int(self.config.pool_timeout * 1000),
        )

    async def disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        if self._client is None:
            raise RuntimeError("Pool not connected")
        yield self._client

    async def fetch(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        raise NotImplementedError("MongoDB does not support SQL fetch")

    async def execute(self, sql: str, params: tuple = ()) -> int:
        raise NotImplementedError("MongoDB does not support SQL execute")


register_driver("mongodb", MotorPool)
register_driver("mongodb+srv", MotorPool)
