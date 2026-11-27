"""Tests for the admin dashboard module (HTMX + Alpine.js)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Load the admin module without triggering the full package import.
# ---------------------------------------------------------------------------


def _load_module(name: str, relative: str):
    """Load a module by file path so we avoid the package-wide Rust deps."""
    full = name
    spec = importlib.util.spec_from_file_location(
        full,
        Path(__file__).resolve().parents[1] / "rivex_admin" / relative,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


_admin = _load_module("rivex_admin_under_test", "__init__.py")
_openapi_stub_path = Path(__file__).resolve().parents[1] / "src" / "rivex" / "openapi.py"


# A fake Rivex app used by the partial / action handlers.
class _FakeApp:
    title = "Test App"
    version = "1.2.3"
    app_name = "Test App"
    powered_by = "Rivex"
    _started_at = None
    _settings_snapshot: dict[str, Any] = {
        "node_env": "test",
        "host": "0.0.0.0",
        "port": 8000,
        "jwt_secret": "super-secret",
        "stripe_secret_key": "sk_test_xxx",
    }
    _log_file: str | None = None
    _routes: list[Any] = []
    _middleware: list[Any] = []
    _controllers: list[Any] = []

    def _reload_settings(self) -> dict[str, Any]:
        return {"reloaded": True}

    async def _ping_database(self) -> int:
        return 7

    def _clear_caches(self) -> int:
        return 3


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_verify_admin_token_accepts_match() -> None:
    assert _admin.verify_admin_token("secret-123", "secret-123") is True


def test_verify_admin_token_rejects_mismatch() -> None:
    assert _admin.verify_admin_token("secret-123", "secret-456") is False


def test_verify_admin_token_rejects_empty() -> None:
    assert _admin.verify_admin_token("", "secret-123") is False
    assert _admin.verify_admin_token("secret-123", "") is False
    assert _admin.verify_admin_token(None, "secret-123") is False


def test_verify_admin_token_rejects_different_lengths() -> None:
    # Lengths differ — must still return False without leaking.
    assert _admin.verify_admin_token("a", "abc") is False


def test_extract_token_from_header() -> None:
    rd = {"headers": [("X-Admin-Token", "tok-abc"), ("Host", "x")]}
    assert _admin._extract_token(rd) == "tok-abc"


def test_extract_token_from_query() -> None:
    rd = {"query_string": "token=xyz&page=1"}
    assert _admin._extract_token(rd) == "xyz"


def test_extract_token_missing() -> None:
    assert _admin._extract_token({}) is None
    assert _admin._extract_token({"headers": [("Host", "x")]}) is None


# ---------------------------------------------------------------------------
# Decorator registry
# ---------------------------------------------------------------------------


def test_admin_partial_decorator_registers() -> None:
    @_admin.admin_partial("test_partial_xyz", title="Test", icon="•")
    def my_p(ctx: _admin.AdminContext) -> str:
        return "<p>ok</p>"

    assert "test_partial_xyz" in _admin._REGISTRY.partials
    meta = _admin._REGISTRY.meta["test_partial_xyz"]
    assert meta["title"] == "Test"
    assert meta["icon"] == "•"
    # Clean up
    del _admin._REGISTRY.partials["test_partial_xyz"]
    del _admin._REGISTRY.meta["test_partial_xyz"]


def test_admin_action_decorator_registers() -> None:
    @_admin.admin_action("test_action_xyz", title="Do it")
    def my_a(ctx: _admin.AdminContext) -> dict[str, Any]:
        return {"ok": True, "message": "done"}

    assert "test_action_xyz" in _admin._REGISTRY.actions
    meta = _admin._REGISTRY.meta["test_action_xyz"]
    assert meta["title"] == "Do it"
    assert meta["dangerous"] == "0"
    del _admin._REGISTRY.actions["test_action_xyz"]
    del _admin._REGISTRY.meta["test_action_xyz"]


def test_admin_action_dangerous_flag() -> None:
    @_admin.admin_action("test_action_danger", dangerous=True)
    def my_a(ctx: _admin.AdminContext) -> dict[str, Any]:
        return {"ok": True}

    assert _admin._REGISTRY.meta["test_action_danger"]["dangerous"] == "1"
    del _admin._REGISTRY.actions["test_action_danger"]
    del _admin._REGISTRY.meta["test_action_danger"]


# ---------------------------------------------------------------------------
# Built-in partials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_overview_renders_app_name() -> None:
    app = _FakeApp()
    out = await _admin._partial_overview(_admin.AdminContext(app=app))
    assert out["service"] == "Test App"
    assert out["version"] == "1.2.3"
    assert out["environment"] == "TEST"
    assert out["bind"] == "0.0.0.0:8000"
    assert out["python"] != ""


@pytest.mark.asyncio
async def test_partial_runtime_shows_metrics() -> None:
    out = await _admin._partial_runtime(_admin.AdminContext(app=_FakeApp()))
    assert out["requests_served"] == 0
    assert out["mounted_routes"] == 0


@pytest.mark.asyncio
async def test_partial_config_redacts_secrets() -> None:
    out = await _admin._partial_config(_admin.AdminContext(app=_FakeApp()))
    jwt_secret_row = next(row for row in out if row["key"] == "jwt_secret")
    stripe_row = next(row for row in out if row["key"] == "stripe_secret_key")
    env_row = next(row for row in out if row["key"] == "node_env")
    assert jwt_secret_row["value"] == "••••••••"
    assert stripe_row["value"] == "••••••••"
    assert env_row["value"] == "test"


@pytest.mark.asyncio
async def test_partial_logs_handles_missing_file() -> None:
    out = await _admin._partial_logs(_admin.AdminContext(app=_FakeApp()))
    assert out["error"] == "No log file configured."


@pytest.mark.asyncio
async def test_partial_logs_reads_file(tmp_path: Path) -> None:
    log = tmp_path / "app.ndjson"
    log.write_text("\n".join(f'{{"msg":"line {i}"}}' for i in range(5)), encoding="utf-8")
    app = _FakeApp()
    app._log_file = str(log)
    out = await _admin._partial_logs(_admin.AdminContext(app=app))
    assert out["error"] is None
    assert len(out["lines"]) == 5
    assert "line 0" in out["lines"][0]


# ---------------------------------------------------------------------------
# Built-in actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_reload_config_invokes_app_method() -> None:
    result = await _admin._action_reload_config(_admin.AdminContext(app=_FakeApp()))
    assert result["ok"] is True
    assert "reloaded" in result["message"].lower()


@pytest.mark.asyncio
async def test_action_ping_db_invokes_app_method() -> None:
    result = await _admin._action_ping_db(_admin.AdminContext(app=_FakeApp()))
    assert result["ok"] is True
    assert "7 ms" in result["message"]


@pytest.mark.asyncio
async def test_action_clear_caches_invokes_app_method() -> None:
    result = await _admin._action_clear_caches(_admin.AdminContext(app=_FakeApp()))
    assert result["ok"] is True
    assert "3" in result["message"]


@pytest.mark.asyncio
async def test_action_reload_handles_missing_method() -> None:
    class Bare:
        pass

    result = await _admin._action_reload_config(_admin.AdminContext(app=Bare()))
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_action_handles_exception() -> None:
    class Broken:
        def _reload_settings(self) -> None:
            raise RuntimeError("boom")

    result = await _admin._action_reload_config(_admin.AdminContext(app=Broken()))
    assert result["ok"] is False
    assert "boom" in result["message"]


# Action result rendering is handled entirely on the React frontend


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


class _FakeServer:
    def __init__(self) -> None:
        self.routes: list[tuple[str, str, Any]] = []

    def add_route(self, method: str, path: str, handler: Any) -> None:
        self.routes.append((method, path, handler))

    def add_websocket_route(self, *a: Any, **kw: Any) -> None:  # pragma: no cover
        pass

    def run(self, *a: Any, **kw: Any) -> None:  # pragma: no cover
        pass


class _FakeRivex:
    """Minimal stand-in for :class:`rivex.Rivex` used by admin route tests."""

    title = "Test"
    version = "1.0.0"
    app_name = "Test"
    powered_by = "Rivex"

    def __init__(self, admin_db: Any = None) -> None:
        self._server = _FakeServer()
        self._mounts: list[tuple[str, Any]] = []
        # By default point the admin DB at a non-existent path so the
        # static-token path is used (no users in the DB).
        if admin_db is None:
            import pathlib
            import tempfile

            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            tmp.close()
            self._admin_db = pathlib.Path(tmp.name)
        else:
            self._admin_db = admin_db

    def mount(self, path: str, app: Any) -> None:
        self._mounts.append((path, app))


def _stub_build_admin_html(**kwargs: Any) -> str:
    """Tiny stub for the admin shell HTML — tests don't need real markup."""
    return "<html>stub-admin-shell</html>"


def _stub_static_files(*args: Any, **kwargs: Any) -> Any:
    """Stand-in for :class:`rivex.staticfiles.StaticFiles` — just a marker."""
    marker = type("StubStaticFiles", (), {})
    return marker()


def test_register_admin_routes_creates_shell_and_partials() -> None:
    app = _FakeRivex()
    _admin.register_admin_routes(
        app,
        base_path="/admin",
        token=None,
        _static_files=_stub_static_files,
    )
    methods_paths = {(m, p) for m, p, _ in app._server.routes}
    # Shell
    assert ("GET", "/admin/") in methods_paths
    assert ("GET", "/admin") in methods_paths
    assert ("GET", "/admin/api/meta") in methods_paths
    # All built-in partials
    for name in _admin._REGISTRY.partials:
        assert ("GET", f"/admin/api/partials/{name}") in methods_paths
    # All built-in actions
    for name in _admin._REGISTRY.actions:
        assert ("POST", f"/admin/api/actions/{name}") in methods_paths
    # Static mount
    assert any(mp[0] == "/admin/static" for mp in app._mounts)
    # Introspection markers
    assert app._admin_mounted is True
    assert app._admin_token_hash == ""  # no token


def test_register_admin_routes_with_token_records_hash() -> None:
    app = _FakeRivex()
    _admin.register_admin_routes(
        app,
        base_path="/_ops",
        token="s3cret",
        _static_files=_stub_static_files,
    )
    # The hash is stored, not the token itself
    assert app._admin_token_hash != "s3cret"
    assert app._admin_token_hash != ""
    assert len(app._admin_token_hash) == 64  # sha256 hex


@pytest.mark.asyncio
async def test_shell_handler_returns_html_when_token_matches(tmp_path: Path, monkeypatch) -> None:
    app = _FakeRivex()
    monkeypatch.setattr(_admin, "_static_admin_path", lambda: tmp_path)
    (tmp_path / "index.html").write_text("react-shell")

    _admin.register_admin_routes(
        app,
        base_path="/admin",
        token="good-token",
        _static_files=_stub_static_files,
    )
    handler = next(h for m, p, h in app._server.routes if (m, p) == ("GET", "/admin/"))
    rd = {"headers": [("X-Admin-Token", "good-token")], "path": "/admin/"}
    result = await handler(rd)
    assert result["status"] == 200
    assert result["body"] == b"react-shell"


# The React SPA shell itself is served unauthenticated so the frontend can load
# and render the login/setup page. Authentication happens on the API endpoints.


@pytest.mark.asyncio
async def test_partial_handler_returns_json_response() -> None:
    app = _FakeRivex()
    _admin.register_admin_routes(
        app,
        base_path="/admin",
        token=None,
        _static_files=_stub_static_files,
    )
    handler = next(
        h for m, p, h in app._server.routes if (m, p) == ("GET", "/admin/api/partials/overview")
    )
    result = await handler({"path": "/admin/api/partials/overview", "headers": []})
    assert result["status"] == 200
    assert result["headers"][0] == ("content-type", "application/json; charset=utf-8")
    import json

    data = json.loads(result["body"].decode("utf-8"))
    assert data["service"] == "Test"


@pytest.mark.asyncio
async def test_action_handler_invokes_builtin() -> None:
    app = _FakeRivex()
    _admin._REGISTRY.actions["reload_config"] = lambda ctx: _FakeApp()._reload_settings()
    _admin.register_admin_routes(
        app,
        base_path="/admin",
        token=None,
        _static_files=_stub_static_files,
    )
    handler = next(
        h
        for m, p, h in app._server.routes
        if (m, p) == ("POST", "/admin/api/actions/reload_config")
    )
    result = await handler({"path": "/admin/api/actions/reload_config", "headers": []})
    assert result["status"] == 200
    import json

    data = json.loads(result["body"].decode("utf-8"))
    assert data["reloaded"] is True


# ---------------------------------------------------------------------------
# Query-string token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_string_token_is_accepted(tmp_path: Path, monkeypatch) -> None:
    app = _FakeRivex()
    monkeypatch.setattr(_admin, "_static_admin_path", lambda: tmp_path)
    (tmp_path / "index.html").write_text("react-shell")

    _admin.register_admin_routes(
        app,
        base_path="/admin",
        token="good-token",
        _static_files=_stub_static_files,
    )
    handler = next(h for m, p, h in app._server.routes if (m, p) == ("GET", "/admin/"))
    rd = {"query_string": "token=good-token&page=1", "path": "/admin/", "headers": []}
    result = await handler(rd)
    assert result["status"] == 200


# ---------------------------------------------------------------------------
# Static React build
# ---------------------------------------------------------------------------


def test_static_admin_dir_has_vendored_files() -> None:
    """The admin dashboard ships with the prebuilt React build index.html."""
    static_dir = _admin._static_admin_path()
    assert static_dir.is_dir()
    assert (static_dir / "index.html").is_file()
    assert (static_dir / "index.html").stat().st_size > 10_000


# ---------------------------------------------------------------------------
# Rivex integration: admin_url / admin_token constructor kwargs
# ---------------------------------------------------------------------------
# These tests are skipped in environments without the compiled Rivex Rust
# extension; the conftest stubs go as far as they can, but several transitive
# imports in ``rivex.gen`` and ``rivex._injection`` still require the
# extension to be present.


def test_rivex_constructor_accepts_admin_url_and_token() -> None:
    """Inspect Rivex.__init__ source for the new parameters (no full import)."""
    pytest.importorskip("rivex_core", reason="Rivex Rust extension not built")
    import inspect

    from rivex.applications.applications import Rivex

    sig = inspect.signature(Rivex.__init__)
    assert "admin_url" in sig.parameters
    assert "admin_token" in sig.parameters


def test_rivex_constructor_keeps_backward_compatible_defaults() -> None:
    pytest.importorskip("rivex_core", reason="Rivex Rust extension not built")
    import inspect

    from rivex.applications.applications import Rivex

    sig = inspect.signature(Rivex.__init__)
    assert sig.parameters["admin_url"].default is None
    assert sig.parameters["admin_token"].default is None
    assert sig.parameters["app_name"].default is None
    assert sig.parameters["powered_by"].default is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
