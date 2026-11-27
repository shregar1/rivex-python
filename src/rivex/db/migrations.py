"""Lightweight SQL migration runner with Alembic interop.

Usage::

    from rivex.db.migrations import Migrator

    migrator = Migrator(app.db.pool("default"), directory="migrations/")

    # Apply all pending migrations
    await migrator.up()

    # Roll back the last batch
    await migrator.down()

Or via CLI::

    rivex db upgrade
    rivex db downgrade
    rivex db history
    rivex db revision -m "add users table"

See Also
--------
Alembic: https://alembic.sqlalchemy.org/
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

_MIGRATIONS_TABLE = "_rivex_migrations"


@dataclass
class Migration:
    """A single migration revision."""

    revision: str
    description: str = ""
    up_sql: str = ""
    down_sql: str = ""
    filename: str = ""
    applied_at: str | None = None


@dataclass
class Migrator:
    """Lightweight SQL migration runner.

    Reads ``.sql`` files from a *directory* and tracks applied revisions
    in a ``_rivex_migrations`` table.  Supports both an embedded SQL
    runner (for SQLite / PostgreSQL) and an Alembic interop mode.

    Args:
        pool: A connected :class:`~rivex.db.DatabasePool`.
        directory: Path to migration files (default ``"migrations/"``).
        table_name: Name of the tracking table.
    """

    pool: Any
    directory: str = "migrations/"
    table_name: str = _MIGRATIONS_TABLE

    def __post_init__(self) -> None:
        self._revisions: list[Migration] | None = None

    # ── File-based migrations ──────────────────────────────────────────

    def _discover(self) -> list[Migration]:
        """Read migration files from *directory* sorted by filename."""
        if self._revisions is not None:
            return self._revisions

        if not os.path.isdir(self.directory):
            self._revisions = []
            return self._revisions

        files = sorted(f for f in os.listdir(self.directory) if f.endswith(".sql"))
        migrations: list[Migration] = []
        for fname in files:
            path = os.path.join(self.directory, fname)
            with open(path) as fh:
                text = fh.read()

            up: list[str] = []
            down: list[str] = []
            current = up
            rev = fname.replace(".sql", "")
            desc = ""
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.upper() == "-- DOWN":
                    current = down
                    continue
                if stripped.upper().startswith("-- REVISION:"):
                    rev = stripped.split(":", 1)[1].strip()
                    continue
                if stripped.upper().startswith("-- DESCRIPTION:"):
                    desc = stripped.split(":", 1)[1].strip()
                    continue
                current.append(line)

            rev = rev or fname.replace(".sql", "")
            desc = desc or ""
            migrations.append(
                Migration(
                    revision=rev,
                    description=desc,
                    up_sql="\n".join(up),
                    down_sql="\n".join(down),
                    filename=fname,
                )
            )
        self._revisions = migrations
        return migrations

    async def _ensure_table(self) -> None:
        """Create the tracking table if it does not exist."""
        async with self.pool.acquire() as conn:
            if hasattr(conn, "execute") and hasattr(conn, "_pool"):
                # asyncpg
                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        revision VARCHAR(255) PRIMARY KEY,
                        description VARCHAR(255) DEFAULT '',
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            else:
                # aiosqlite / generic
                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        revision TEXT PRIMARY KEY,
                        description TEXT DEFAULT '',
                        applied_at TEXT DEFAULT (datetime('now'))
                    )
                    """
                )

    async def _applied(self) -> set[str]:
        """Return the set of already-applied revision ids."""
        await self._ensure_table()
        async with self.pool.acquire() as conn:
            if hasattr(conn, "fetch"):
                rows = await conn.fetch(f"SELECT revision FROM {self.table_name}")
            else:
                cur = await conn.execute(f"SELECT revision FROM {self.table_name}")
                rows = await cur.fetchall()
            return {row["revision"] for row in rows}

    async def up(self, target: str | None = None) -> list[str]:
        """Apply all pending migrations (or up to *target*).

        Returns the list of revision ids that were applied.
        """
        applied = await self._applied()
        migrations = self._discover()
        applied_revisions: list[str] = []

        for m in migrations:
            if m.revision in applied:
                continue
            await self._run_sql(m.up_sql)
            await self._mark_applied(m)
            applied_revisions.append(m.revision)
            if target and m.revision == target:
                break

        return applied_revisions

    async def down(self, target: str | None = None, *, limit: int = 1) -> list[str]:
        """Roll back migrations (or down to *target*).

        By default rolls back one revision.  Set *limit* to ``0``
        to roll back all applied migrations, or pass a *target*
        revision to stop at that revision (exclusive).

        Returns the list of revision ids that were rolled back.
        """
        applied = await self._applied()
        migrations = self._discover()
        rolled: list[str] = []

        for m in reversed(migrations):
            if m.revision not in applied:
                continue
            if target and m.revision == target:
                break
            if m.down_sql.strip():
                await self._run_sql(m.down_sql)
            await self._mark_reverted(m)
            rolled.append(m.revision)
            if limit and len(rolled) >= limit:
                break

        return rolled

    async def history(self) -> list[Migration]:
        """Return all migrations with their applied status."""
        applied = await self._applied()
        migrations = self._discover()
        for m in migrations:
            m.applied_at = "applied" if m.revision in applied else "pending"
        return migrations

    # ── SQL execution ──────────────────────────────────────────────────

    async def _run_sql(self, sql: str) -> None:
        """Execute the given SQL script statement by statement.

        Statements are split on top-level semicolons; the implementation
        inspects the connection to pick the right calling convention so
        the same code works against asyncpg and aiosqlite-style backends.

        Args:
            sql: Raw SQL text containing one or more semicolon-separated
                statements. An empty or whitespace-only string is a
                no-op.
        """
        statements = [s.strip() for s in re.split(r";\s*", sql) if s.strip()]
        if not statements:
            return
        async with self.pool.acquire() as conn:
            for stmt in statements:
                if hasattr(conn, "execute") and hasattr(conn, "_pool"):
                    await conn.execute(stmt)
                else:
                    await conn.execute(stmt)

    async def _mark_applied(self, m: Migration) -> None:
        """Record migration *m* in the tracking table.

        Uses the asyncpg-style ``$1`` / ``$2`` placeholders when the
        connection exposes an internal ``_pool`` attribute and the
        ``?`` placeholder style otherwise.

        Args:
            m: The :class:`Migration` whose revision and description
                should be persisted.
        """
        async with self.pool.acquire() as conn:
            if hasattr(conn, "execute") and hasattr(conn, "_pool"):
                await conn.execute(
                    f"INSERT INTO {self.table_name} (revision, description) VALUES ($1, $2)",
                    m.revision,
                    m.description,
                )
            else:
                await conn.execute(
                    f"INSERT INTO {self.table_name} (revision, description) VALUES (?, ?)",
                    (m.revision, m.description),
                )

    async def _mark_reverted(self, m: Migration) -> None:
        """Remove migration *m*'s row from the tracking table.

        Args:
            m: The :class:`Migration` whose tracking row should be
                deleted after a successful rollback.
        """
        async with self.pool.acquire() as conn:
            if hasattr(conn, "execute") and hasattr(conn, "_pool"):
                await conn.execute(
                    f"DELETE FROM {self.table_name} WHERE revision = $1", m.revision
                )
            else:
                await conn.execute(
                    f"DELETE FROM {self.table_name} WHERE revision = ?", (m.revision,)
                )

    # ── Alembic interop ────────────────────────────────────────────────

    async def alembic_upgrade(self, target: str = "head") -> None:
        """Delegate to Alembic's upgrade command.

        Requires ``alembic`` to be installed and an ``alembic.ini``
        present in the project root.
        """
        _run_alembic("upgrade", target)

    async def alembic_downgrade(self, target: str = "-1") -> None:
        """Delegate to Alembic's downgrade command.

        Args:
            target: Revision to downgrade to. Defaults to ``"-1"``,
                Alembic's shorthand for "one step back".
        """
        _run_alembic("downgrade", target)

    async def alembic_revision(
        self, message: str = "", autogenerate: bool = False
    ) -> None:
        """Create a new Alembic revision.

        Args:
            message: Revision message used as the migration's docstring.
            autogenerate: When ``True`` ``--autogenerate`` is passed so
                Alembic diffs the live database against the model
                metadata.
        """
        args = ["revision", "--autogenerate"] if autogenerate else ["revision"]
        if message:
            args.extend(["-m", message])
        _run_alembic(*args)


def _run_alembic(*args: str) -> None:
    """Run an Alembic CLI command programmatically."""
    try:
        from alembic.config import CommandLine

        CommandLine().main(args)
    except ImportError:
        raise RuntimeError(
            "alembic is not installed. ``pip install alembic``"
        ) from None
