from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from rivex import Rivex
from rivex.db import DatabaseConfig, DatabasePool, DatabaseRegistry, register_driver
from rivex.db.migrations import Migrator

# Register the SQLite driver (stdlib, always available)
import rivex.db.sqlite  # noqa: F401


class TestDatabaseConfig:
    def test_defaults(self):
        cfg = DatabaseConfig(url="sqlite:///:memory:")
        assert cfg.pool_size == 10
        assert cfg.max_overflow == 20
        assert cfg.min_size == 10
        assert cfg.max_size == 30
        assert cfg.pool_timeout == 30.0

    def test_custom(self):
        cfg = DatabaseConfig(url="postgresql://localhost/db", pool_size=5, max_overflow=10)
        assert cfg.min_size == 5
        assert cfg.max_size == 15


class TestDatabaseRegistry:
    def test_configure_and_pool_before_connect(self):
        reg = DatabaseRegistry()
        reg.configure("default", url="sqlite:///:memory:")
        assert "default" in reg

        with pytest.raises(RuntimeError, match="not connected"):
            reg.pool("default")

    def test_configure_and_pool_after_connect(self):
        import asyncio

        reg = DatabaseRegistry()
        reg.configure("default", url="sqlite:///:memory:")
        asyncio.run(reg.connect_all())
        pool = reg.pool("default")
        assert isinstance(pool, DatabasePool)
        asyncio.run(reg.disconnect_all())
        # Configs are retained after disconnect (can reconnect)
        assert "default" in reg
        with pytest.raises(RuntimeError, match="not connected"):
            reg.pool("default")

    def test_missing_name_before_connect(self):
        reg = DatabaseRegistry()
        with pytest.raises(RuntimeError, match="not connected"):
            reg.pool("nonexistent")

    def test_missing_name_after_connect(self):
        import asyncio

        reg = DatabaseRegistry()
        reg.configure("default", url="sqlite:///:memory:")
        asyncio.run(reg.connect_all())
        with pytest.raises(KeyError):
            reg.pool("nonexistent")
        asyncio.run(reg.disconnect_all())

    def test_getitem(self):
        import asyncio

        reg = DatabaseRegistry()
        reg.configure("default", url="sqlite:///:memory:")
        asyncio.run(reg.connect_all())
        pool = reg["default"]
        assert isinstance(pool, DatabasePool)
        asyncio.run(reg.disconnect_all())

    def test_getitem_missing_after_connect(self):
        import asyncio

        reg = DatabaseRegistry()
        reg.configure("default", url="sqlite:///:memory:")
        asyncio.run(reg.connect_all())
        with pytest.raises(KeyError):
            reg["nonexistent"]
        asyncio.run(reg.disconnect_all())


class TestSqlitePool:
    @pytest.mark.asyncio
    async def test_connect_and_query(self):
        reg = DatabaseRegistry()
        reg.configure("default", url="sqlite:///:memory:")
        await reg.connect_all()
        pool = reg.pool("default")

        async with pool.acquire() as conn:
            await conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
            await conn.execute("INSERT INTO test (val) VALUES (?)", ("hello",))
            cur = await conn.execute("SELECT * FROM test")
            rows = await cur.fetchall()
            assert len(rows) == 1
            assert rows[0]["val"] == "hello"

        await reg.disconnect_all()

    @pytest.mark.asyncio
    async def test_database_lifecycle(self):
        app = Rivex()
        app.db.configure("default", url="sqlite:///:memory:")
        await app.db.connect_all()
        pool = app.db.pool("default")
        assert isinstance(pool, DatabasePool)

        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")

        await app.db.disconnect_all()
        assert not app.db._connected

    @pytest.mark.asyncio
    async def test_file_based_sqlite(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            reg = DatabaseRegistry()
            reg.configure("default", url=f"sqlite:///{db_path}")
            await reg.connect_all()
            pool = reg.pool("default")

            async with pool.acquire() as conn:
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT)"
                )
                await conn.execute("INSERT INTO items (name) VALUES (?)", ("test",))

            await reg.disconnect_all()

            # Verify file persists
            reg2 = DatabaseRegistry()
            reg2.configure("default", url=f"sqlite:///{db_path}")
            await reg2.connect_all()
            pool2 = reg2.pool("default")
            async with pool2.acquire() as conn:
                cur = await conn.execute("SELECT name FROM items")
                rows = await cur.fetchall()
                assert len(rows) == 1
                assert rows[0]["name"] == "test"
            await reg2.disconnect_all()
        finally:
            os.unlink(db_path)


class TestMigrations:
    @pytest.mark.asyncio
    async def test_up_and_down(self, tmp_path: Path):
        reg = DatabaseRegistry()
        reg.configure("default", url="sqlite:///:memory:")
        await reg.connect_all()
        pool = reg.pool("default")

        # Create migration files
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "001_users.sql").write_text(
            "-- REVISION: 001\n"
            "-- DESCRIPTION: create users table\n"
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);\n"
            "-- DOWN\n"
            "DROP TABLE users;\n"
        )
        (mig_dir / "002_posts.sql").write_text(
            "-- REVISION: 002\n"
            "-- DESCRIPTION: create posts\n"
            "CREATE TABLE posts (id INTEGER PRIMARY KEY, title TEXT);\n"
            "-- DOWN\n"
            "DROP TABLE posts;\n"
        )

        migrator = Migrator(pool, directory=str(mig_dir))

        # Apply up
        applied = await migrator.up()
        assert applied == ["001", "002"]

        # Verify tables exist
        async with pool.acquire() as conn:
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row["name"] for row in await cur.fetchall()}
            assert "users" in tables
            assert "posts" in tables

        # Second run should be no-op
        applied2 = await migrator.up()
        assert applied2 == []

        # Roll back one
        rolled = await migrator.down()
        assert rolled == ["002"]
        async with pool.acquire() as conn:
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row["name"] for row in await cur.fetchall()}
            assert "posts" not in tables
            assert "users" in tables

        # Roll back the rest
        rolled2 = await migrator.down()
        assert rolled2 == ["001"]
        async with pool.acquire() as conn:
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row["name"] for row in await cur.fetchall()}
            assert "users" not in tables

        await reg.disconnect_all()

    @pytest.mark.asyncio
    async def test_history(self, tmp_path: Path):
        reg = DatabaseRegistry()
        reg.configure("default", url="sqlite:///:memory:")
        await reg.connect_all()
        pool = reg.pool("default")

        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "001_init.sql").write_text(
            "-- REVISION: 001\nCREATE TABLE t (id INT);\n"
        )

        migrator = Migrator(pool, directory=str(mig_dir))
        await migrator.up()
        history = await migrator.history()
        assert len(history) == 1
        assert history[0].revision == "001"

        await reg.disconnect_all()
