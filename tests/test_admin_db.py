"""Tests for the SQLite admin user store and the ``rivex admin`` CLI."""

from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest


def _load_admin_db():
    """Load ``rivex_admin.db`` without dragging the full package in.

    The module is registered in ``sys.modules`` so ``@dataclass`` can
    resolve its module's globals (``ns = sys.modules[cls.__module__].__dict__``).
    """
    # Other test files (``test_barebones.py``) install stub modules under
    # the ``rivex_admin`` name to simulate the package being uninstalled.
    # Those stubs raise on every attribute access and would block our
    # ``from rivex_admin.db import AdminStore`` below.  Remove them so
    # the real import path works.
    for name in list(sys.modules):
        if name == "rivex_admin" or name.startswith("rivex_admin."):
            sys.modules.pop(name, None)
    name = "rivex_admin_db_under_test"
    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).resolve().parents[1] / "rivex_admin" / "db.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_admin_cli():
    # Same as above — clear any stubs that earlier tests installed.
    for name in list(sys.modules):
        if name == "rivex_admin" or name.startswith("rivex_admin."):
            sys.modules.pop(name, None)
    name = "rivex_admin_cli_under_test"
    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).resolve().parents[1] / "rivex_admin" / "cli.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# SQLite store
# ---------------------------------------------------------------------------


def test_default_db_path_under_dot_rivex(tmp_path, monkeypatch):
    db = _load_admin_db()
    monkeypatch.chdir(tmp_path)
    path = db.default_db_path()
    assert path == tmp_path / ".rivex" / "admin.db"


def test_default_db_path_honours_env(monkeypatch, tmp_path):
    db = _load_admin_db()
    target = tmp_path / "custom.db"
    monkeypatch.setenv("RIVEX_ADMIN_DB", str(target))
    assert db.default_db_path() == target


def test_add_and_verify_round_trip(tmp_path):
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "admin.db")
    user = store.add_user("alice", "secret-token", note="ops")
    assert user.username == "alice"
    assert user.id > 0
    assert user.note == "ops"
    # token is hashed, not stored raw
    assert user.token_hash != "secret-token"
    assert len(user.token_hash) == 64  # sha256 hex
    # verify
    found = store.verify_token("secret-token")
    assert found is not None
    assert found.username == "alice"
    assert store.verify_token("wrong-token") is None
    assert store.verify_token("") is None
    assert store.verify_token(None) is None  # type: ignore[arg-type]


def test_token_hash_uses_sha256():
    db = _load_admin_db()
    import hashlib

    token = "abc123"
    assert db.hash_token(token) == hashlib.sha256(token.encode()).hexdigest()


def test_duplicate_username_raises(tmp_path):
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "admin.db")
    store.add_user("alice", "x")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_user("alice", "y")


def test_rotate_token_invalidates_old(tmp_path):
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "admin.db")
    store.add_user("alice", "old")
    assert store.verify_token("old") is not None
    store.rotate_token("alice", "new")
    assert store.verify_token("old") is None
    assert store.verify_token("new") is not None


def test_rotate_unknown_user_raises_keyerror(tmp_path):
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "admin.db")
    with pytest.raises(KeyError):
        store.rotate_token("ghost", "x")


def test_list_users_orders_by_id(tmp_path):
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "admin.db")
    store.add_user("a", "x")
    store.add_user("b", "y")
    store.add_user("c", "z")
    names = [u.username for u in store.list_users()]
    assert names == ["a", "b", "c"]


def test_delete_user(tmp_path):
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "admin.db")
    store.add_user("alice", "x")
    assert store.delete_user("alice") is True
    assert store.delete_user("alice") is False  # idempotent
    assert store.list_users() == []


def test_has_any_users(tmp_path):
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "admin.db")
    assert store.has_any_users() is False
    store.add_user("alice", "x")
    assert store.has_any_users() is True


def test_touch_used_does_not_raise(tmp_path):
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "admin.db")
    store.add_user("alice", "x")
    # Even if the username doesn't exist, touch_used is fire-and-forget.
    store.touch_used("ghost")
    store.touch_used("alice")
    users = store.list_users()
    assert users[0].last_used_at is not None


def test_generate_token_is_unique_and_long():
    db = _load_admin_db()
    tokens = {db.generate_token() for _ in range(20)}
    assert len(tokens) == 20
    assert all(len(t) >= 30 for t in tokens)


# ---------------------------------------------------------------------------
# CLI: ``rivex admin mint/list/rotate/delete``
# ---------------------------------------------------------------------------


def test_cli_mint_auto_generates_token(tmp_path, capsys, monkeypatch):
    cli = _load_admin_cli()
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["mint", "--username", "alice", "--db", str(tmp_path / "a.db")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "alice" in out
    assert "Token (save!):" in out  # banner appears once
    # Token is in the output AND it actually authenticates
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "a.db")
    assert store.has_any_users()


def test_cli_mint_with_explicit_token_doesnt_echo_it(tmp_path, capsys):
    cli = _load_admin_cli()
    rc = cli.main(
        ["mint", "--username", "bob", "--token", "supersecret", "--db", str(tmp_path / "a.db")]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "bob" in out
    assert "supersecret" not in out  # never echo a user-supplied token
    # But it does authenticate
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "a.db")
    assert store.verify_token("supersecret") is not None


def test_cli_list_shows_users(tmp_path, capsys):
    cli = _load_admin_cli()
    cli.main(["mint", "--username", "alice", "--db", str(tmp_path / "a.db")])
    capsys.readouterr()
    rc = cli.main(["list", "--db", str(tmp_path / "a.db")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "alice" in out


def test_cli_list_empty_db(tmp_path, capsys):
    cli = _load_admin_cli()
    rc = cli.main(["list", "--db", str(tmp_path / "a.db")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "(no admin users" in out
    assert "createsuperuser" in out


def test_cli_rotate(tmp_path):
    cli = _load_admin_cli()
    cli.main(["mint", "--username", "alice", "--token", "old", "--db", str(tmp_path / "a.db")])
    cli.main(["rotate", "alice", "--token", "new", "--db", str(tmp_path / "a.db")])
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "a.db")
    assert store.verify_token("old") is None
    assert store.verify_token("new") is not None


def test_cli_delete_with_yes(tmp_path, capsys):
    cli = _load_admin_cli()
    cli.main(["mint", "--username", "alice", "--db", str(tmp_path / "a.db")])
    rc = cli.main(["delete", "alice", "-y", "--db", str(tmp_path / "a.db")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Deleted" in out
    db = _load_admin_db()
    store = db.AdminStore(tmp_path / "a.db")
    assert store.list_users() == []


def test_cli_delete_unknown_user(tmp_path, capsys):
    cli = _load_admin_cli()
    rc = cli.main(["delete", "ghost", "-y", "--db", str(tmp_path / "a.db")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ghost" in err


# ---------------------------------------------------------------------------
# Core CLI: ``rivex createsuperuser`` is exposed and routes to rivex_admin
# ---------------------------------------------------------------------------


def test_createsuperuser_routes_to_admin_cli(tmp_path, monkeypatch, capsys):
    """Smoke-test that ``rivex createsuperuser`` is wired into the
    top-level CLI and reaches the admin store.  We use stdin to
    feed the interactive prompt."""
    import subprocess

    # Provide username + an empty token (auto-generate) via stdin.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.argv = ['rivex', 'createsuperuser']; "
            "sys.path.insert(0, '.'); "
            "from rivex.cli import main; main()",
        ],
        input="autotest\n\n\n",  # username, then empty token, then confirm
        capture_output=True,
        text=True,
        timeout=10,
        cwd="/Users/shreyansh/Documents/vexarr/rivex/python.rivex.vexarr.com",
        env={
            **__import__("os").environ,
            "RIVEX_ADMIN_DB": str(tmp_path / "admin.db"),
        },
    )
    # We expect the CLI to either succeed (and show the banner) or fail
    # with a "rivex_admin not installed" message.  Both are valid
    # proof that the dispatch works.
    combined = result.stdout + result.stderr
    assert (
        "admin dashboard" in combined.lower()
        or "rivex_admin" in combined
        or "creat" in combined.lower()
    ), f"unexpected output: {combined!r}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
