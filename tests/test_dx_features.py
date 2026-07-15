"""Tests for the three DX features added in this branch:

* ``rivex.Settings`` — env-var-driven Schema subclass.
* ``rivex.SessionMiddleware`` — signed-cookie sessions wired to
  ``request.session``.
* ``rivex.reload.run_with_reload`` — file-watching hot-reload helper
  (smoke-tested, not run end-to-end since that needs a subprocess).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rivex import Request, Rivex, SessionMiddleware, Settings, TestClient

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class _AppSettings(Settings):
    database_url: str
    secret_key: str
    debug: bool = False
    port: int = 8000


def test_settings_from_dict() -> None:
    cfg = _AppSettings.from_dict(
        {"database_url": "postgres://x", "secret_key": "shh", "debug": True}
    )
    assert cfg.database_url == "postgres://x"
    assert cfg.secret_key == "shh"
    assert cfg.debug is True
    assert cfg.port == 8000  # default


def test_settings_from_env_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://from-env")
    monkeypatch.setenv("SECRET_KEY", "shh-env")
    monkeypatch.setenv("DEBUG", "true")
    cfg = _AppSettings.from_env()
    assert cfg.database_url == "postgres://from-env"
    assert cfg.secret_key == "shh-env"
    assert cfg.debug is True


class _PrefixedSettings(Settings):
    model_config = {"env_prefix": "MYAPP_"}
    host: str = "localhost"


def test_settings_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYAPP_HOST", "0.0.0.0")
    cfg = _PrefixedSettings.from_env()
    assert cfg.host == "0.0.0.0"


def test_settings_dotenv_file(monkeypatch: pytest.MonkeyPatch) -> None:
    # Wipe any inherited env so the .env values are what gets read.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with tempfile.TemporaryDirectory() as d:
        env_path = Path(d) / ".env"
        env_path.write_text(
            '# a comment\nDATABASE_URL="postgres://from-dotenv"\nSECRET_KEY=k\nPORT=9090\n'
        )

        class _S(Settings):
            model_config = {"env_file": str(env_path)}
            database_url: str
            secret_key: str
            port: int = 8000

        cfg = _S.from_env()
        assert cfg.database_url == "postgres://from-dotenv"
        assert cfg.secret_key == "k"
        assert cfg.port == 9090


def test_settings_env_overrides_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    # If both ``.env`` and ``os.environ`` define a key, the live env wins.
    monkeypatch.setenv("SECRET_KEY", "from-real-env")
    with tempfile.TemporaryDirectory() as d:
        env_path = Path(d) / ".env"
        env_path.write_text("SECRET_KEY=from-dotenv\nDATABASE_URL=x\n")

        class _S(Settings):
            model_config = {"env_file": str(env_path)}
            database_url: str
            secret_key: str

        cfg = _S.from_env()
        assert cfg.secret_key == "from-real-env"


# ---------------------------------------------------------------------------
# SessionMiddleware
# ---------------------------------------------------------------------------


def test_session_middleware_round_trip() -> None:
    app = Rivex()
    app.add_middleware(SessionMiddleware, secret_key="0" * 32)

    @app.get("/count")
    async def count(request: Request):
        n = (request.session.get("n") or 0) + 1
        request.session["n"] = n
        return {"n": n}

    with TestClient(app) as client:
        r1 = client.get("/count")
        assert r1.json()["n"] == 1
        # Round-trip the cookie back to the server to bump the counter
        cookie = r1.headers.get("set-cookie", "")
        assert "session=" in cookie
        r2 = client.get("/count", headers={"cookie": cookie.split(";")[0]})
        assert r2.json()["n"] == 2


def test_session_middleware_tampered_cookie_is_dropped() -> None:
    app = Rivex()
    app.add_middleware(SessionMiddleware, secret_key="0" * 32)

    @app.get("/")
    async def root(request: Request):
        return {"got": dict(request.session)}

    with TestClient(app) as client:
        r = client.get("/", headers={"cookie": "session=not-a-valid-token"})
        # We don't raise — we just present an empty session.
        assert r.status_code == 200
        assert r.json() == {"got": {}}


def test_session_middleware_no_set_cookie_when_unchanged() -> None:
    """If a handler reads but never writes the session, no Set-Cookie is sent.

    Avoids burning a Set-Cookie header (and an extra round-trip of
    cookie data) on every GET that doesn't touch state.
    """
    app = Rivex()
    app.add_middleware(SessionMiddleware, secret_key="0" * 32)

    @app.get("/")
    async def root(request: Request):
        _ = request.session.get("anything")
        return {"ok": True}

    with TestClient(app) as client:
        r = client.get("/")
        # No Set-Cookie because session was untouched
        assert "set-cookie" not in {k.lower() for k in r.headers}


# ---------------------------------------------------------------------------
# Hot-reload helper — smoke test (no subprocess)
# ---------------------------------------------------------------------------


def test_reload_snapshot_picks_up_py_files() -> None:
    """``_snapshot`` returns a dict of every ``*.py`` file under ``roots``.

    The full ``run_with_reload`` loop spawns a subprocess and watches
    indefinitely, so we don't run that here — we just verify the
    file-discovery helper does what the watcher relies on.
    """
    from rivex.cli.reload import _snapshot

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "app.py").write_text("x = 1")
        (root / "skipme.txt").write_text("not python")
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "app.cpython-313.pyc").write_text("")

        snap = _snapshot([root], (".py",))
        names = {Path(p).name for p in snap}
        assert "app.py" in names
        assert "skipme.txt" not in names
        # __pycache__ traversal is suppressed
        assert not any(".pyc" in p for p in snap)
