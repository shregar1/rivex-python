"""
S3 adapter — requires ``aioboto3``.

This module is part of *rivex-adapter* and auto-registers the
``s3://`` scheme when imported.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse, parse_qs

from rivex.db import DatabaseConfig, DatabasePool, register_driver


class S3Pool(DatabasePool):
    """Connection pool for S3-compatible object storage via ``aioboto3``."""

    def __init__(self, config: DatabaseConfig) -> None:
        super().__init__(config)
        self._session: Any = None
        self._client: Any = None

    async def connect(self) -> None:
        import aioboto3

        parsed = self._parse_url()
        self._session = aioboto3.Session(
            aws_access_key_id=parsed.get("access_key"),
            aws_secret_access_key=parsed.get("secret_key"),
            region_name=parsed.get("region", "us-east-1"),
        )
        self._client = await self._session.client(
            "s3",
            endpoint_url=parsed.get("endpoint_url"),
        ).__aenter__()

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None

    def _parse_url(self) -> dict[str, str]:
        parsed = urlparse(self.config.url)
        result: dict[str, str] = {}
        if parsed.username:
            result["access_key"] = parsed.username
        if parsed.password:
            result["secret_key"] = parsed.password
        result["region"] = parsed.hostname or "us-east-1"
        if parsed.path:
            result["bucket"] = parsed.path.lstrip("/")
        qs = parse_qs(parsed.query)
        if "endpoint" in qs:
            result["endpoint_url"] = qs["endpoint"][0]
        return result

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        if self._client is None:
            raise RuntimeError("S3 client not connected")
        yield self._client

    async def fetch(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        raise NotImplementedError("S3 does not support SQL fetch")

    async def execute(self, sql: str, params: tuple = ()) -> int:
        raise NotImplementedError("S3 does not support SQL execute")


register_driver("s3", S3Pool)
