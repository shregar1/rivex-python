"""
Rivex Database Integration — core abstractions.

This module provides the abstract ``DatabasePool`` base class and
the ``DatabaseRegistry`` that powers ``app.db``.  No database drivers
are imported at this level.

Driver implementations live in sibling modules (``rivex/db/sqlite.py``,
``rivex/db/asyncpg.py``, etc.) and register themselves with
:func:`register_driver` at import time.

Typical usage::

    from rivex import Rivex
    import rivex.db.sqlite   # registers the sqlite driver  # noqa: F401

    app = Rivex()
    app.db.configure("default", url="sqlite:///app.db")

    @app.get("/users")
    async def list_users(db=app.db["default"]):
        async with db.acquire() as conn:
            ...
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

__all__ = [
    "DatabaseConfig",
    "DatabasePool",
    "DatabaseRegistry",
    "register_driver",
]

# ── URL scheme → driver registry ──

_DRIVERS: dict[str, type[DatabasePool]] = {}


def register_driver(scheme: str, pool_cls: type[DatabasePool]) -> None:
    _DRIVERS[scheme] = pool_cls


def _detect_driver(url: str) -> type[DatabasePool]:
    scheme = url.split("://", 1)[0].lower()
    scheme = {
        "postgres": "postgresql",
        "postgresql+asyncpg": "postgresql",
        "postgres+asyncpg": "postgresql",
        "sqlite3": "sqlite",
    }.get(scheme, scheme)
    cls = _DRIVERS.get(scheme)
    if cls is None:
        raise ValueError(
            f"Unsupported database URL scheme {scheme!r}. "
            f"Available drivers: {list(_DRIVERS)}"
        )
    return cls


# ── Configuration ──


@dataclass
class DatabaseConfig:
    """Configuration for a database connection pool.

    Args:
        url: Connection URL (e.g. ``"postgresql://user:pass@localhost/db"``).
        pool_size: Number of persistent connections to keep in the pool.
        max_overflow: Maximum number of additional transient connections.
        pool_timeout: Seconds to wait for a connection from the pool.
        echo: Log all SQL statements.
        kwargs: Extra keyword arguments passed to the driver's pool constructor.
    """

    url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: float = 30.0
    echo: bool = False
    kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def min_size(self) -> int:
        return self.pool_size

    @property
    def max_size(self) -> int:
        return self.pool_size + self.max_overflow


# ── Pool base class ──


class DatabasePool:
    """Abstract async connection pool.

    Subclasses implement :meth:`connect`, :meth:`disconnect` and
    :meth:`acquire` for a specific database driver.
    """

    config: DatabaseConfig

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config

    async def connect(self) -> None:
        """Create the underlying connection pool (called on startup)."""

    async def disconnect(self) -> None:
        """Close the underlying connection pool (called on shutdown)."""

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        """Acquire a connection from the pool (async context manager).

        Usage::

            async with pool.acquire() as conn:
                await conn.fetch("SELECT 1")
        """
        raise NotImplementedError
        yield  # pragma: no cover

    @classmethod
    async def create(cls, config: DatabaseConfig) -> DatabasePool:
        """Factory: create, connect and return a pool."""
        pool = cls(config)
        await pool.connect()
        return pool


# ── Registry ──


class DatabaseRegistry:
    """Holds named database configurations and creates pools on startup.

    Accessed via ``app.db``.  Pools are created during startup via
    :meth:`connect_all` (called automatically by the lifespan hook).
    """

    def __init__(self) -> None:
        self._configs: dict[str, DatabaseConfig] = {}
        self._pools: dict[str, DatabasePool] = {}
        self._connected = False

    def configure(self, name: str, url: str, **kwargs: Any) -> None:
        """Register a database configuration.

        Args:
            name: Logical name (e.g. ``"default"``, ``"analytics"``).
            url: Connection URL.
            **kwargs: Override :class:`DatabaseConfig` defaults.
        """
        self._configs[name] = DatabaseConfig(url=url, **kwargs)

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError(
                "Database pool not connected. "
                "Ensure ``app.db.connect_all()`` is called during startup "
                "(e.g. via the lifespan hook)."
            )

    def pool(self, name: str = "default") -> DatabasePool:
        """Return the connected pool for *name* (synchronous, no I/O)."""
        self._ensure_connected()
        if name not in self._pools:
            raise KeyError(f"No database configured for {name!r}")
        return self._pools[name]

    async def connect_all(self) -> None:
        """Connect all configured pools.  Called during startup."""
        errors: list[tuple[str, Exception]] = []
        for name, config in self._configs.items():
            try:
                driver = _detect_driver(config.url)
                pool = await driver.create(config)
                self._pools[name] = pool
            except ImportError as e:
                errors.append((name, e))
            except Exception as e:
                errors.append((name, e))
        self._connected = True
        if errors:
            import warnings
            for name, err in errors:
                warnings.warn(
                    f"Database {name!r} failed to connect: {err}",
                    stacklevel=2,
                )

    async def disconnect_all(self) -> None:
        """Disconnect all pools.  Called during shutdown."""
        for pool in self._pools.values():
            await pool.disconnect()
        self._pools.clear()
        self._connected = False

    def __getitem__(self, name: str) -> DatabasePool:
        return self.pool(name)

    def __contains__(self, name: str) -> bool:
        return name in self._pools or name in self._configs
