"""Behavioral tests for the native ``rivex`` CLI (``rivex.cli.cli``).

These exercise the command layer for real — not just ``--help`` text — for
the commands ported from the deprecated standalone ``rivex-cli`` package
(``openapi``, ``bench``, ``routes --format``, ``--env-file``) plus a
regression test for the duplicate-route bug that used to crash any app
registering ``GET /`` alongside the auto-mounted health route.
"""

from __future__ import annotations

import http.server
import json
import socket
import socketserver
import subprocess
import sys
import threading
import time

import httpx
import pytest

from rivex.cli.cli import load_env_file, main

# ---------------------------------------------------------------------------
# App fixture: write a small importable Rivex app into an isolated dir.
# ---------------------------------------------------------------------------


_APP_PY = """\
from rivex import Rivex

app = Rivex(title="CliTest", version="2.0.0")


@app.get("/ping")
async def ping():
    return {"pong": True}


@app.get("/items/{item_id}")
async def item(item_id: int):
    return {"id": item_id}
"""


@pytest.fixture
def cli_app(tmp_path, monkeypatch):
    """Make ``app:app`` importable from a clean cwd."""
    (tmp_path / "app.py").write_text(_APP_PY)
    monkeypatch.chdir(tmp_path)
    # ``_import_app`` caches by module name; clear stale entries between tests.
    sys.modules.pop("app", None)
    yield tmp_path
    sys.modules.pop("app", None)


# ---------------------------------------------------------------------------
# version / help
# ---------------------------------------------------------------------------


def test_version(capsys):
    main(["version"])
    out = capsys.readouterr().out
    assert "Rivex" in out


def test_help_lists_ported_commands(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for cmd in ("routes", "openapi", "bench"):
        assert cmd in out


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


def test_routes_table(cli_app, capsys):
    main(["routes", "app:app"])
    out = capsys.readouterr().out
    assert "METHOD" in out and "PATH" in out and "HANDLER" in out
    assert "/ping" in out and "/items/{item_id}" in out


def test_routes_json(cli_app, capsys):
    main(["routes", "app:app", "--format", "json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    paths = {r["path"] for r in data}
    assert "/ping" in paths and "/items/{item_id}" in paths
    by_path = {r["path"]: r for r in data}
    assert by_path["/ping"]["method"] == "GET"
    assert by_path["/ping"]["name"] == "ping"


# ---------------------------------------------------------------------------
# openapi
# ---------------------------------------------------------------------------


def test_openapi_stdout(cli_app, capsys):
    main(["openapi", "app:app"])
    spec = json.loads(capsys.readouterr().out)
    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["title"] == "CliTest"
    assert spec["info"]["version"] == "2.0.0"
    assert "/ping" in spec["paths"]


def test_openapi_output_file(cli_app, capsys, tmp_path):
    out_file = tmp_path / "spec.json"
    main(["openapi", "app:app", "-o", str(out_file), "--indent", "0"])
    assert "OpenAPI spec written to" in capsys.readouterr().out
    spec = json.loads(out_file.read_text())
    assert spec["openapi"] == "3.1.0"


# ---------------------------------------------------------------------------
# bench — exercise against a real in-process HTTP server.
# ---------------------------------------------------------------------------


class _OKHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server convention
        body = b"ok"
        self.send_response(200)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence stderr noise
        pass


@pytest.fixture
def live_http_server():
    server = socketserver.TCPServer(("127.0.0.1", 0), _OKHandler)
    server.allow_reuse_address = True
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_bench_runs(live_http_server, capsys):
    main(["bench", live_http_server, "-n", "20", "-c", "4"])
    out = capsys.readouterr().out
    assert "Benchmarking" in out
    assert "Successful:     20" in out
    assert "Failed:         0" in out
    assert "200=20" in out


def test_bench_connection_refused(capsys):
    # Nothing listening on an ephemeral port — all requests fail, but the
    # command must still complete cleanly with a structured report.
    main(["bench", "http://127.0.0.1:1", "-n", "4", "-c", "2"])
    out = capsys.readouterr().out
    assert "Failed:         4" in out


# ---------------------------------------------------------------------------
# load_env_file
# ---------------------------------------------------------------------------


def test_load_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('FOO_X=bar\nQUOTED_X="a b"\n# comment\nBARE_X=hi # note\n')
    for k in ("FOO_X", "QUOTED_X", "BARE_X"):
        monkeypatch.delenv(k, raising=False)
    count = load_env_file(str(env))
    assert count == 3
    import os

    assert os.environ["FOO_X"] == "bar"
    assert os.environ["QUOTED_X"] == "a b"
    assert os.environ["BARE_X"] == "hi"


def test_load_env_file_missing_returns_zero():
    assert load_env_file("/no/such/path/.env") == 0


def test_load_env_file_does_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("EXISTING_X", "original")
    env = tmp_path / ".env"
    env.write_text("EXISTING_X=overwritten\n")
    load_env_file(str(env))
    import os

    assert os.environ["EXISTING_X"] == "original"


# ---------------------------------------------------------------------------
# Regression: the auto-mounted health route (health_url defaults to "/")
# must NOT collide with a user-registered GET / route. This crashed every
# app that defined its own root route while docs were enabled.
# ---------------------------------------------------------------------------


class _RecordingServer:
    """Fake server that records every add_route() and rejects duplicates."""

    def __init__(self):
        self.added: list[tuple[str, str]] = []

    def add_route(self, method, path, handler, **kwargs):
        if (method, path) in self.added:
            raise ValueError(f"duplicate route {method} {path}")
        self.added.append((method, path))

    def add_const_route(self, *args, **kwargs):
        pass

    def add_websocket_route(self, *args, **kwargs):
        pass


def test_health_route_skipped_when_user_owns_root(monkeypatch):
    from rivex import Rivex

    app = Rivex(title="t", version="0.0.1")  # full defaults: health_url="/", docs on

    @app.get("/")
    async def root():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    fake = _RecordingServer()
    # Pretend the user routes were already registered by _drive_rust_server's
    # main loop, then run the openapi/health auto-mount phase.
    registered = {"/", "/health"}
    app._register_openapi_routes(fake, registered)

    # No GET / may have been added by the health auto-mount (user owns it),
    # and there must be no duplicate of any path.
    assert ("GET", "/") not in fake.added
    assert len(fake.added) == len(set(fake.added))


# ---------------------------------------------------------------------------
# dev / run — exercise the subprocess path end-to-end with real HTTP traffic.
# The original audit flagged dev/run as "help-text only" tests — exactly why
# the duplicate-route crash shipped. These tests would have caught it.
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=0.5) as client:
                r = client.get(f"http://127.0.0.1:{port}/ping")
                if r.status_code in (200, 404):
                    return
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError):
            pass
        time.sleep(0.25)
    raise AssertionError(f"server on port {port} did not bind within {timeout}s")


def _terminate(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _env() -> dict[str, str]:
    import os
    from pathlib import Path
    env = dict(os.environ)
    src_dir = str(Path(__file__).parent.parent / "src")
    env["PYTHONPATH"] = f"{src_dir}:{env.get('PYTHONPATH', '')}" if "PYTHONPATH" in env else src_dir
    return env


def test_run_serves_app(cli_app):
    """`rivex run app:app` actually binds the port and serves real traffic."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "rivex.cli.cli", "run", "app:app", "--port", str(port)],
        cwd=cli_app,
        env=_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        with httpx.Client(timeout=2.0) as client:
            ping = client.get(f"http://127.0.0.1:{port}/ping")
            item = client.get(f"http://127.0.0.1:{port}/items/42")
            missing = client.get(f"http://127.0.0.1:{port}/no/such/route")
        assert ping.status_code == 200 and ping.json() == {"pong": True}
        assert item.status_code == 200 and item.json() == {"id": 42}
        assert missing.status_code == 404
    finally:
        _terminate(proc)


def test_run_regression_used_to_crash_with_root_and_health(cli_app):
    """The exact config that used to crash `rivex run` before the
    health-route collision was fixed: GET / + GET /health + docs on.

    If this regresses, any scaffolded app with a root route will not start.
    """
    crashapp = cli_app / "crashapp.py"
    crashapp.write_text(
        "from rivex import Rivex\n"
        "app = Rivex(title='crash')\n"
        "@app.get('/')\n"
        "async def r(): return {'ok': True}\n"
        "@app.get('/health')\n"
        "async def h(): return {'h': True}\n"
    )
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "rivex.cli.cli", "run", "crashapp:app", "--port", str(port)],
        cwd=cli_app,
        env=_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        with httpx.Client(timeout=2.0) as client:
            root = client.get(f"http://127.0.0.1:{port}/")
            health = client.get(f"http://127.0.0.1:{port}/health")
        assert root.status_code == 200 and root.json() == {"ok": True}
        assert health.status_code == 200 and health.json() == {"h": True}
    finally:
        _terminate(proc)


def test_dev_serves_app(cli_app):
    """`rivex dev app:app` binds and serves. Uses --no-reload to keep
    the test fast and deterministic; reload itself is covered by
    uvicorn/watchfiles upstream tests, not ours."""
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "rivex.cli.cli",
            "dev",
            "app:app",
            "--port",
            str(port),
            "--no-reload",
        ],
        cwd=cli_app,
        env=_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        with httpx.Client(timeout=2.0) as client:
            ping = client.get(f"http://127.0.0.1:{port}/ping")
        assert ping.status_code == 200 and ping.json() == {"pong": True}
    finally:
        _terminate(proc)
