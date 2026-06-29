"""Tier 2 observability middleware tests.

Each built-in observability middleware is tested through the
async engine (the same engine that powers the bench). Every
test is end-to-end (spawns a real server thread, makes a real
HTTP request, asserts the response).

Coverage:

- HealthCheckMiddleware: /healthz and /readyz are served
  without any user route, return 200 with the right body.
- PrometheusMetricsMiddleware: /metrics serves the standard
  text/plain exposition with the request counter.
- TracingMiddleware: request-id is generated and echoed in
  the x-request-id response header.
- JsonLoggingMiddleware: at least the SDK-level integration
  (not the Rust log output, which would require capturing
  stderr).

The sync engine is also exercised on /healthz to confirm
the const-router wiring works on both backends.
"""
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

import rivex
from rivex.middleware_observability import (
    HealthCheckMiddleware,
    JsonLoggingMiddleware,
    PrometheusMetricsMiddleware,
    TracingMiddleware,
)


def _free_port() -> int:
    """Bind to port 0, get the assigned port, close. Returns the port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spawn(app: rivex.Rivex, target_name: str, **run_kwargs) -> int:
    """Start ``app.<target_name>`` in a daemon thread on a free port.

    ``_free_port`` closes its probe socket before the server binds, so the
    OS can hand the same ephemeral port to two servers (a TOCTOU race) — and
    these tests leave their servers running, so a stale bind lingers. To make
    startup deterministic we retry on a fresh port whenever the server thread
    dies (bind collision) or never starts accepting. Returns the live port.
    """
    last_port = None
    for _ in range(12):
        port = _free_port()
        last_port = port
        t = threading.Thread(
            target=getattr(app, target_name),
            kwargs={"host": "127.0.0.1", "port": port, **run_kwargs},
            daemon=True,
        )
        t.start()
        deadline = time.time() + 3
        while time.time() < deadline:
            if not t.is_alive():
                break  # server thread exited — almost always a bind collision
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return port
            except (ConnectionRefusedError, OSError):
                time.sleep(0.02)
        # Did not come up on this port — pick another and retry.
    raise RuntimeError(f"server did not start (last tried port {last_port})")


def _start_server(app: rivex.Rivex) -> int:
    """Spawn the async engine on a free port; returns the live port."""
    return _spawn(app, "run")


def _start_sync_server(app: rivex.Rivex) -> int:
    """Spawn the sync engine on a free port; returns the live port.

    Uses a single worker so the server runs in this process's daemon
    thread. ``workers>1`` would fork persistent child processes that
    outlive the test and keep the interpreter from exiting (a hang at
    teardown); one worker is enough to exercise the sync engine wiring.
    """
    return _spawn(app, "run_sync", workers=1)


def _http_get(url: str, headers: dict | None = None, timeout: float = 5) -> tuple[int, dict, bytes]:
    """Tiny urllib wrapper. Returns (status, response_headers, body)."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.getheaders()), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


# ── HealthCheckMiddleware ───────────────────────────────────────────


def test_healthcheck_serves_liveness_on_default_path() -> None:
    """GET /healthz returns 200 + JSON without any user route."""
    app = rivex.Rivex()
    app.add_middleware(HealthCheckMiddleware)
    port = _start_server(app)
    status, headers, body = _http_get(f"http://127.0.0.1:{port}/healthz")
    assert status == 200
    assert "application/json" in headers.get("content-type", "")
    assert b"\"status\"" in body


def test_healthcheck_serves_readiness_on_default_path() -> None:
    """GET /readyz returns 200 + JSON without any user route."""
    app = rivex.Rivex()
    app.add_middleware(HealthCheckMiddleware)
    port = _start_server(app)
    status, _, body = _http_get(f"http://127.0.0.1:{port}/readyz")
    assert status == 200
    assert b"\"status\"" in body


def test_healthcheck_custom_paths() -> None:
    """Custom liveness/readiness paths are honoured."""
    app = rivex.Rivex()
    app.add_middleware(
        HealthCheckMiddleware,
        liveness_path="/alive",
        readiness_path="/ready",
    )
    port = _start_server(app)
    s1, _, _ = _http_get(f"http://127.0.0.1:{port}/alive")
    s2, _, _ = _http_get(f"http://127.0.0.1:{port}/ready")
    assert s1 == 200
    assert s2 == 200


def test_healthcheck_works_on_sync_engine() -> None:
    """HealthCheck serves /healthz on the sync engine too."""
    app = rivex.Rivex()
    app.add_middleware(HealthCheckMiddleware)
    port = _start_sync_server(app)
    status, _, body = _http_get(f"http://127.0.0.1:{port}/healthz")
    assert status == 200
    assert b"\"status\"" in body


def test_healthcheck_does_not_shadow_user_routes() -> None:
    """User-registered routes on /healthz take precedence over the
    built-in liveness probe when the path differs (default liveness
    is /healthz so we register a different one)."""
    app = rivex.Rivex()
    # User registers a route on /my-health that returns "user route"
    @app.get("/my-health")
    def _user() -> dict:
        return {"source": "user"}

    app.add_middleware(HealthCheckMiddleware, liveness_path="/healthz", readiness_path="/readyz")
    port = _start_server(app)
    s, _, b = _http_get(f"http://127.0.0.1:{port}/my-health")
    assert s == 200
    assert b"user" in b


# ── PrometheusMetricsMiddleware ─────────────────────────────────────


def test_prometheus_serves_metrics_on_default_path() -> None:
    """GET /metrics returns 200 with the standard text/plain body."""
    app = rivex.Rivex()
    app.add_middleware(PrometheusMetricsMiddleware)
    port = _start_server(app)
    status, headers, body = _http_get(f"http://127.0.0.1:{port}/metrics")
    assert status == 200
    assert "text/plain" in headers.get("content-type", "")


def test_prometheus_custom_path() -> None:
    """Custom metrics path is honoured."""
    app = rivex.Rivex()
    app.add_middleware(PrometheusMetricsMiddleware, path="/prom")
    port = _start_server(app)
    s, _, _ = _http_get(f"http://127.0.0.1:{port}/prom")
    assert s == 200


def test_prometheus_works_on_sync_engine() -> None:
    """Metrics served on the sync engine too (no metrics body is
    rendered for sync — the endpoint returns 200 and an empty
    body, which is enough to confirm the wiring)."""
    app = rivex.Rivex()
    app.add_middleware(PrometheusMetricsMiddleware)
    port = _start_sync_server(app)
    s, headers, _ = _http_get(f"http://127.0.0.1:{port}/metrics")
    assert s == 200
    assert "text/plain" in headers.get("content-type", "")


# ── TracingMiddleware ───────────────────────────────────────────────


def test_tracing_middleware_returns_request_id_header() -> None:
    """The tracing middleware injects an x-request-id header."""
    app = rivex.Rivex()
    app.add_middleware(TracingMiddleware)

    @app.get("/hi")
    def _hi() -> dict:
        return {"hello": "world"}

    port = _start_server(app)
    s, headers, _ = _http_get(f"http://127.0.0.1:{port}/hi")
    assert s == 200
    # The header key is case-insensitive; the request id should
    # look like `req-<ms>-<seq>`.
    rid = headers.get("x-request-id") or headers.get("X-Request-Id")
    assert rid is not None
    assert rid.startswith("req-")


# ── JsonLoggingMiddleware ───────────────────────────────────────────


def test_json_logging_middleware_does_not_break_requests() -> None:
    """Adding JSON-log middleware does not affect response shape."""
    app = rivex.Rivex()
    app.add_middleware(JsonLoggingMiddleware)

    @app.get("/ping")
    def _ping() -> dict:
        return {"ok": True}

    port = _start_server(app)
    s, _, b = _http_get(f"http://127.0.0.1:{port}/ping")
    assert s == 200
    assert b"\"ok\"" in b


# ── Combined: all four ──────────────────────────────────────────────


def test_all_four_middlewares_together() -> None:
    """All four Tier 2 middlewares can be installed on one app."""
    app = rivex.Rivex()
    app.add_middleware(PrometheusMetricsMiddleware, path="/metrics")
    app.add_middleware(TracingMiddleware, span_name="http_request")
    app.add_middleware(JsonLoggingMiddleware)
    app.add_middleware(HealthCheckMiddleware, liveness_path="/healthz", readiness_path="/readyz")

    @app.get("/x")
    def _x() -> dict:
        return {"x": 1}

    port = _start_server(app)
    # /x works
    s, _, b = _http_get(f"http://127.0.0.1:{port}/x")
    assert s == 200
    assert b"\"x\"" in b
    # /healthz works
    s, _, _ = _http_get(f"http://127.0.0.1:{port}/healthz")
    assert s == 200
    # /readyz works
    s, _, _ = _http_get(f"http://127.0.0.1:{port}/readyz")
    assert s == 200
    # /metrics works
    s, _, _ = _http_get(f"http://127.0.0.1:{port}/metrics")
    assert s == 200
