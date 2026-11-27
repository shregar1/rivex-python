from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class AutoMigrator:
    """Inspects current database schema vs declared models and generates
    migration SQL files.

    Usage::

        migrator = AutoMigrator(app.db)
        plan = await migrator.detect_changes()
        await migrator.write_migration("auto_add_tables", plan)
    """

    def __init__(self, pool, migrations_dir: str = "migrations"):
        self._pool = pool
        self._migrations_dir = Path(migrations_dir)

    async def _get_existing_tables(self) -> set[str]:
        """Query INFORMATION_SCHEMA for current tables."""
        try:
            rows = await self._pool.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            return {r["table_name"] for r in rows}
        except Exception:
            # Fallback for SQLite
            rows = await self._pool.fetch(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            return {r["name"] for r in rows}

    async def _get_table_columns(self, table: str) -> list[dict]:
        """Return the column descriptors currently defined for *table*.

        Tries the PostgreSQL ``INFORMATION_SCHEMA.columns`` view first
        and falls back to an empty list if the query fails — most often
        because the backend is SQLite which exposes a different schema
        catalogue.

        Args:
            table: Name of the table whose columns should be read.

        Returns:
            A list of column descriptor dicts with keys ``name``,
            ``type``, ``nullable``, ``default`` and ``max_length``. Empty
            when the lookup fails or the table does not exist.
        """
        try:
            rows = await self._pool.fetch(
                "SELECT column_name, data_type, is_nullable, "
                "       column_default, character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_name = $1",
                table,
            )
            return [
                {
                    "name": r["column_name"],
                    "type": r["data_type"],
                    "nullable": r["is_nullable"] == "YES",
                    "default": r["column_default"],
                    "max_length": r["character_maximum_length"],
                }
                for r in rows
            ]
        except Exception:
            return []

    async def detect_changes(self) -> dict:
        """Compare declared models against database schema.

        Returns a migration plan dict with keys:
        - ``add_tables``: list of (table_name, columns)
        - ``drop_tables``: list of table names
        - ``add_columns``: list of (table, column_def)
        - ``drop_columns``: list of (table, column_name)
        """
        existing_tables = await self._get_existing_tables()

        # Discover declared models from app.db.models()
        try:
            from rivex.applications.applications import Rivex
            app = Rivex.get_current()
        except Exception:
            return {"add_tables": [], "drop_tables": [], "add_columns": [], "drop_columns": []}

        model_registry = getattr(app.db, "_models", {})

        add_tables: list[tuple[str, list]] = []
        drop_tables: list[str] = []

        for name, model_cls in model_registry.items():
            table = getattr(model_cls, "__table__", name.lower())
            if table not in existing_tables:
                cols = getattr(model_cls, "__columns__", [{"name": "id", "type": "SERIAL PRIMARY KEY"}])
                add_tables.append((table, cols))

        for table in existing_tables:
            if table.startswith("pg_") or table.startswith("sqlite_"):
                continue
            if table not in [getattr(m, "__table__", n.lower()) for n, m in model_registry.items()]:
                drop_tables.append(table)

        add_columns: list[tuple[str, dict]] = []
        drop_columns: list[tuple[str, str]] = []

        for name, model_cls in model_registry.items():
            table = getattr(model_cls, "__table__", name.lower())
            if table in existing_tables:
                existing_cols = await self._get_table_columns(table)
                existing_names = {c["name"] for c in existing_cols}
                declared_cols = getattr(model_cls, "__columns__", [])
                for col in declared_cols:
                    if col["name"] not in existing_names:
                        add_columns.append((table, col))
                for col in existing_cols:
                    if col["name"] not in {c["name"] for c in declared_cols}:
                        drop_columns.append((table, col["name"]))

        return {
            "add_tables": add_tables,
            "drop_tables": drop_tables,
            "add_columns": add_columns,
            "drop_columns": drop_columns,
        }

    def _col_to_sql(self, col: dict) -> str:
        """Render a single column descriptor as a SQL column definition.

        Args:
            col: Column descriptor with ``name``, ``type``, optional
                ``nullable`` and ``default`` keys.

        Returns:
            The SQL fragment for the column, including type, nullability
            and default clauses.
        """
        col_type = col.get("type", "TEXT").upper()
        nullable = "" if col.get("nullable", True) else " NOT NULL"
        default = f" DEFAULT {col['default']}" if col.get("default") else ""
        return f"{col['name']} {col_type}{nullable}{default}"

    def generate_sql(self, plan: dict) -> str:
        """Translate a migration plan into a single SQL script.

        The plan is rendered in the order ``add_tables``,
        ``drop_tables``, ``add_columns`` and ``drop_columns``. Each
        statement is terminated with a semicolon and the result is the
        statements joined by newlines.

        Args:
            plan: Migration plan as produced by :meth:`detect_changes`.

        Returns:
            The SQL text ready to be written to disk or executed.
        """
        lines: list[str] = []
        for table, cols in plan.get("add_tables", []):
            col_defs = ", ".join(self._col_to_sql(c) for c in cols)
            lines.append(f"CREATE TABLE {table} ({col_defs});")
        for table in plan.get("drop_tables", []):
            lines.append(f"DROP TABLE IF EXISTS {table} CASCADE;")
        for table, col in plan.get("add_columns", []):
            lines.append(f"ALTER TABLE {table} ADD COLUMN {self._col_to_sql(col)};")
        for table, col_name in plan.get("drop_columns", []):
            lines.append(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col_name};")
        return "\n".join(lines)

    async def write_migration(self, name: str, plan: dict | None = None) -> str:
        """Generate the SQL for *plan* and write it to a timestamped file.

        When *plan* is omitted the current schema diff is detected via
        :meth:`detect_changes`. The destination filename is composed of
        the current UTC timestamp and *name*, and the migrations
        directory is created on demand.

        Args:
            name: Short slug appended to the timestamp; used as the
                migration's logical name.
            plan: Optional pre-computed migration plan.

        Returns:
            The path of the written migration file as a string.
        """
        if plan is None:
            plan = await self.detect_changes()
        sql = self.generate_sql(plan)
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{name}.sql"
        migration_path = self._migrations_dir / filename
        self._migrations_dir.mkdir(parents=True, exist_ok=True)
        migration_path.write_text(sql)
        return str(migration_path)

    async def apply(self, migration_file: str) -> dict:
        """Execute the SQL in *migration_file* statement by statement.

        Args:
            migration_file: Path to a ``.sql`` file with semicolon
                separated DDL statements.

        Returns:
            A dict with ``"applied"`` (list of statement previews that
            succeeded) and ``"errors"`` (list of ``{"statement", "error"}``
            entries for statements that failed). Execution continues past
            individual failures.
        """
        sql = Path(migration_file).read_text()
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        results = {"applied": [], "errors": []}
        for stmt in statements:
            try:
                await self._pool.execute(stmt)
                results["applied"].append(stmt[:80])
            except Exception as e:
                results["errors"].append({"statement": stmt[:80], "error": str(e)})
        return results

    def print_plan(self, plan: dict) -> str:
        """Return a human-readable rendering of *plan*.

        Args:
            plan: Migration plan as produced by :meth:`detect_changes`.

        Returns:
            A multi-line summary suitable for printing to a terminal. If
            the plan is empty in every category the string
            ``"No changes detected."`` is returned instead.
        """
        lines: list[str] = ["Migration Plan:"]
        for table, cols in plan.get("add_tables", []):
            lines.append(f"  + CREATE TABLE {table} ({len(cols)} columns)")
        for table in plan.get("drop_tables", []):
            lines.append(f"  - DROP TABLE {table}")
        for table, col in plan.get("add_columns", []):
            lines.append(f"  + ALTER TABLE {table} ADD {col['name']} ({col.get('type', 'TEXT')})")
        for table, col_name in plan.get("drop_columns", []):
            lines.append(f"  - ALTER TABLE {table} DROP {col_name}")
        if not any(plan.values()):
            return "No changes detected."
        return "\n".join(lines)
