"""SQLite-backed admin authentication store.

The dashboard's auth check has historically been a single static
``admin_token`` string.  This module turns it into a multi-user store:

* :class:`AdminStore` — connection-managed access to ``admin_users``
* :func:`default_db_path` — sensible per-project location
* SHA-256 token hashing, constant-time verification, last-used
  tracking.

Used by both the dashboard (read path) and the
``rivex admin mint/rotate/list/delete`` CLI (write path).  Lives in
its own module so the CLI can import it without dragging in
HTMX/Alpine.js.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    UNIQUE NOT NULL,
    token_hash    TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    last_used_at  TEXT,
    note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_admin_token_hash ON admin_users(token_hash);
"""


@dataclass(frozen=True)
class AdminUser:
    """A row in the ``admin_users`` table."""

    id: int
    username: str
    token_hash: str
    created_at: str
    last_used_at: str | None
    note: str | None

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "token_hash": self.token_hash,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "note": self.note,
        }


def hash_token(token: str) -> str:
    """SHA-256 hex digest of *token* — what we persist."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token(nbytes: int = 32) -> str:
    """Cryptographically random URL-safe token (default 32 bytes = 256 bits)."""
    return secrets.token_urlsafe(nbytes)


def default_db_path() -> Path:
    """Per-project default — ``./.rivex/admin.db``.

    Override with the ``RIVEX_ADMIN_DB`` environment variable.
    """
    import os

    env = os.environ.get("RIVEX_ADMIN_DB")
    if env:
        return Path(env)
    return Path.cwd() / ".rivex" / "admin.db"


class AdminStore:
    """Connection-managed access to the admin_users table.

    SQLite connections aren't safe to share across threads, so we
    keep a per-thread connection.  ``__init__`` does not open the
    connection — that happens lazily on first use.
    """

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path is not None else default_db_path()
        self._lock = threading.Lock()
        self._local = threading.local()

    @property
    def path(self) -> Path:
        return self._path

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self._path),
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False,
                isolation_level=None,  # autocommit; we manage transactions explicitly
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)
            self._local.conn = conn
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn()
        with self._lock:
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ── writes ───────────────────────────────────────────────────

    def add_user(
        self,
        username: str,
        token: str,
        *,
        note: str | None = None,
    ) -> AdminUser:
        """Insert a new admin user.

        ``token`` is the *raw* token (what the user will paste into
        the dashboard).  Only the SHA-256 hash is stored.
        """
        token_hash = hash_token(token)
        with self._tx() as conn:
            cur = conn.execute(
                "INSERT INTO admin_users (username, token_hash, note) VALUES (?, ?, ?)",
                (username, token_hash, note),
            )
            row_id = cur.lastrowid
        assert row_id is not None, "INSERT always populates lastrowid"
        return self.get_user(row_id)  # type: ignore[return-value]

    def rotate_token(self, username: str, new_token: str) -> AdminUser:
        token_hash = hash_token(new_token)
        with self._tx() as conn:
            cur = conn.execute(
                "UPDATE admin_users SET token_hash = ? WHERE username = ?",
                (token_hash, username),
            )
            if cur.rowcount == 0:
                raise KeyError(f"no admin user named {username!r}")
        return self.get_user_by_name(username)  # type: ignore[return-value]

    def delete_user(self, username: str) -> bool:
        with self._tx() as conn:
            cur = conn.execute("DELETE FROM admin_users WHERE username = ?", (username,))
            return cur.rowcount > 0

    def touch_used(self, username: str) -> None:
        """Mark *username* as just-used.  Fire-and-forget — never fails."""
        try:
            with self._tx() as conn:
                conn.execute(
                    "UPDATE admin_users SET last_used_at = datetime('now') WHERE username = ?",
                    (username,),
                )
        except Exception:  # pragma: no cover
            pass

    # ── reads ────────────────────────────────────────────────────

    def list_users(self) -> list[AdminUser]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, username, token_hash, created_at, last_used_at, note "
            "FROM admin_users ORDER BY id"
        ).fetchall()
        return [u for u in (_row_to_user(r) for r in rows) if u is not None]

    def get_user(self, user_id: int) -> AdminUser | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT id, username, token_hash, created_at, last_used_at, note "
            "FROM admin_users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return _row_to_user(row) if row else None

    def get_user_by_name(self, username: str) -> AdminUser | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT id, username, token_hash, created_at, last_used_at, note "
            "FROM admin_users WHERE username = ?",
            (username,),
        ).fetchone()
        return _row_to_user(row) if row else None

    def verify_token(self, token: str) -> AdminUser | None:
        """Return the matching admin if *token* is valid, else None.

        Uses ``hmac.compare_digest`` for constant-time comparison.
        """
        if not token:
            return None
        token_hash = hash_token(token)
        conn = self._conn()
        row = conn.execute(
            "SELECT id, username, token_hash, created_at, last_used_at, note "
            "FROM admin_users WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        # Defence in depth — compare the digests we got with what we computed.
        if not hmac.compare_digest(row["token_hash"], token_hash):
            return None
        return _row_to_user(row)

    def has_any_users(self) -> bool:
        conn = self._conn()
        row = conn.execute("SELECT 1 FROM admin_users LIMIT 1").fetchone()
        return row is not None


def _row_to_user(row: sqlite3.Row | None) -> AdminUser | None:
    if row is None:
        return None
    return AdminUser(
        id=row["id"],
        username=row["username"],
        token_hash=row["token_hash"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        note=row["note"],
    )


__all__ = [
    "AdminStore",
    "AdminUser",
    "default_db_path",
    "generate_token",
    "hash_token",
]
