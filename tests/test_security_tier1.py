"""Tier 1 security middleware tests.

Each protection is tested through the sync engine (which exposes
the Rust core's security pipeline directly). Every test is end-to-end
(spawns a real server thread, makes a real HTTP request, asserts the
response). We deliberately don't use the in-process TestClient here
because the security middleware is implemented in Rust and is only
reachable through the full request path.
"""
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

import rivex


def _free_port() -> int:
    """Bind to port 0, get the assigned port, close. Returns the port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(app: rivex.Rivex) -> int:
    """Start the engine on a free port in a daemon thread, retrying on a
    fresh port if the bind races (``_free_port`` closes its probe socket
    before the server binds, so the OS can hand the same port to two
    servers). Returns the live port once it is accepting connections."""
    last_port = None
    for _ in range(12):
        port = _free_port()
        last_port = port

        def _run(p=port) -> None:
            try:
                app.run_async(host="127.0.0.1", port=p)
            except Exception:
                pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if not t.is_alive():
                break  # thread exited — almost always a bind collision
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    return port
            except OSError:
                time.sleep(0.05)
    raise RuntimeError(f"server did not start (last tried port {last_port})")


def _http(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    data: bytes | None = None,
) -> urllib.request.addinfourl | urllib.error.HTTPError:
    """Issue a request. Returns either a response or an HTTPError."""
    req = urllib.request.Request(url, method=method, data=data)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        return urllib.request.urlopen(req, timeout=3)
    except urllib.error.HTTPError as e:
        return e


@pytest.fixture
def hello_app():
    """An app with a single GET /hello route and Tier 1 security."""
    app = rivex.Rivex(docs_url=None, redoc_url=None, openapi_url=None, landing_page=False)

    @app.get("/hello")
    def hello():
        import json
        return {"hello": "world"}

    return app


# ── 1. CORS ──────────────────────────────────────────────────────


def test_cors_preflight_returns_204_with_all_cors_headers(hello_app):
    port = _free_port()
    hello_app.with_security(
        cors={
            "allow_origins": ["https://example.com"],
            "allow_methods": ["GET", "POST"],
            "allow_headers": ["content-type", "authorization"],
            "allow_credentials": True,
            "max_age": 3600,
        },
    )
    port = _start_server(hello_app)
    r = _http("OPTIONS", f"http://127.0.0.1:{port}/hello", headers={
        "Origin": "https://example.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert r.status == 204
    assert r.headers.get("access-control-allow-origin") == "https://example.com"
    assert r.headers.get("access-control-allow-credentials") == "true"
    assert r.headers.get("vary") == "Origin"
    assert "POST" in r.headers.get("access-control-allow-methods", "")
    assert "content-type" in r.headers.get("access-control-allow-headers", "")
    assert r.headers.get("access-control-max-age") == "3600"


def test_cors_actual_request_adds_origin_header(hello_app):
    port = _free_port()
    hello_app.with_security(
        cors={"allow_origins": ["https://example.com"],
              "allow_methods": ["GET"], "max_age": 60},
    )
    port = _start_server(hello_app)
    r = _http("GET", f"http://127.0.0.1:{port}/hello",
              headers={"Origin": "https://example.com"})
    assert r.status == 200
    assert r.headers.get("access-control-allow-origin") == "https://example.com"
    assert r.headers.get("vary") == "Origin"


# ── 2. CSRF ──────────────────────────────────────────────────────


def test_csrf_unsafe_without_token_is_rejected(hello_app):
    port = _free_port()
    hello_app.with_security(csrf={"enforce": True})
    port = _start_server(hello_app)
    # POST without a CSRF token returns 403.
    r = _http("POST", f"http://127.0.0.1:{port}/hello", data=b"x")
    assert r.status == 403


def test_csrf_safe_method_does_not_require_token(hello_app):
    port = _free_port()
    hello_app.with_security(csrf={"enforce": True})
    port = _start_server(hello_app)
    # GET is a safe method — no CSRF check.
    r = _http("GET", f"http://127.0.0.1:{port}/hello")
    assert r.status == 200


# ── 3. HSTS ──────────────────────────────────────────────────────


def test_hsts_header_present(hello_app):
    port = _free_port()
    hello_app.with_security(
        hsts={"max_age": 31_536_000, "include_subdomains": True, "preload": True},
    )
    port = _start_server(hello_app)
    r = _http("GET", f"http://127.0.0.1:{port}/hello")
    sts = r.headers.get("strict-transport-security")
    assert sts is not None
    assert "max-age=31536000" in sts
    assert "includeSubDomains" in sts
    assert "preload" in sts


# ── 4. Trusted-host validation ──────────────────────────────────


def test_trusted_host_rejects_unknown(hello_app):
    port = _free_port()
    hello_app.with_security(trusted_hosts=["example.com", "*.example.com"])
    port = _start_server(hello_app)
    r = _http("GET", f"http://127.0.0.1:{port}/hello",
              headers={"Host": "evil.com"})
    assert r.status == 421


def test_trusted_host_accepts_known(hello_app):
    port = _free_port()
    hello_app.with_security(trusted_hosts=["example.com", "*.example.com"])
    port = _start_server(hello_app)
    r = _http("GET", f"http://127.0.0.1:{port}/hello",
              headers={"Host": "example.com"})
    assert r.status == 200
    r = _http("GET", f"http://127.0.0.1:{port}/hello",
              headers={"Host": "api.example.com"})
    assert r.status == 200


def test_trusted_host_wildcard(hello_app):
    port = _free_port()
    hello_app.with_security(trusted_hosts=["*.example.com"])
    port = _start_server(hello_app)
    r = _http("GET", f"http://127.0.0.1:{port}/hello",
              headers={"Host": "api.example.com"})
    assert r.status == 200
    r = _http("GET", f"http://127.0.0.1:{port}/hello",
              headers={"Host": "api.staging.example.com"})
    assert r.status == 200


# ── 5. XSS escaping (text/html only) ────────────────────────────


def test_xss_escapes_html_responses(hello_app):
    port = _free_port()
    # Add an HTML route with raw user data that contains a script tag.
    @hello_app.get("/greet")
    def greet():
        from rivex.http.responses import HTMLResponse
        return HTMLResponse("<html><body>Hello <script>alert(1)</script></body></html>")

    hello_app.with_security(xss={"auto_escape_html": True})
    port = _start_server(hello_app)
    r = _http("GET", f"http://127.0.0.1:{port}/greet")
    body = r.read().decode()
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
    # JSON responses are NOT escaped (they're already safe).
    r = _http("GET", f"http://127.0.0.1:{port}/hello")
    json_body = r.read().decode()
    assert "<" not in json_body or r.headers.get("content-type", "").startswith("application/json")


# ── 6. Request body size limit ───────────────────────────────────


def test_oversize_body_rejected(hello_app):
    port = _free_port()

    @hello_app.post("/echo")
    def echo_post():
        return ""

    hello_app.with_security(max_body_size=1024)
    port = _start_server(hello_app)
    r = _http("POST", f"http://127.0.0.1:{port}/echo",
              data=b"X" * 2048,
              headers={"Content-Type": "text/plain"})
    assert r.status == 413


def test_undersize_body_allowed(hello_app):
    port = _free_port()

    @hello_app.post("/echo")
    def echo_post_small():
        return ""

    hello_app.with_security(max_body_size=1024)
    port = _start_server(hello_app)
    r = _http("POST", f"http://127.0.0.1:{port}/echo",
              data=b"X" * 256,
              headers={"Content-Type": "text/plain"})
    assert r.status == 200


# ── Composition: all 6 enabled together ──────────────────────────


def test_all_tier1_enabled_together():
    """Stack all six protections and confirm each still does its job."""
    app = rivex.Rivex(docs_url=None, redoc_url=None, openapi_url=None, landing_page=False)

    @app.get("/hello")
    def hello():
        return {"hello": "world"}

    @app.post("/echo")
    def echo():
        return ""

    app.with_security(
        cors={"allow_origins": ["https://example.com"],
              "allow_methods": ["GET", "POST"], "max_age": 3600},
        csrf={"enforce": True},
        hsts={"max_age": 31_536_000, "include_subdomains": True, "preload": False},
        trusted_hosts=["example.com", "127.0.0.1"],
        xss={"auto_escape_html": True},
        max_body_size=4096,
    )
    port = _free_port()
    port = _start_server(app)

    # HSTS
    r = _http("GET", f"http://127.0.0.1:{port}/hello",
              headers={"Host": "127.0.0.1"})
    assert "max-age=31536000" in r.headers.get("strict-transport-security", "")

    # Trusted host reject
    r = _http("GET", f"http://127.0.0.1:{port}/hello",
              headers={"Host": "evil.com"})
    assert r.status == 421

    # CORS preflight
    r = _http("OPTIONS", f"http://127.0.0.1:{port}/hello", headers={
        "Host": "127.0.0.1",
        "Origin": "https://example.com",
        "Access-Control-Request-Method": "POST",
    })
    assert r.status == 204
    assert r.headers.get("access-control-allow-origin") == "https://example.com"

    # CSRF unsafe without token
    r = _http("POST", f"http://127.0.0.1:{port}/hello",
              headers={"Host": "127.0.0.1"}, data=b"{}")
    assert r.status == 403

    # Body limit. Use a valid CSRF token so we get past the CSRF
    # check and reach the body-size check.
    r = _http("POST", f"http://127.0.0.1:{port}/echo",
              headers={"Host": "127.0.0.1",
                       "Content-Type": "text/plain",
                       "Cookie": "XSRF-TOKEN=abc123",
                       "X-CSRF-Token": "abc123"},
              data=b"X" * 8192)
    assert r.status == 413


# ── ``with_security`` builder ───────────────────────────────────


def test_with_security_builder_returns_self_for_chaining():
    app = rivex.Rivex()
    result = app.with_security(
        cors={"allow_origins": ["*"], "allow_methods": ["GET"], "max_age": 60},
    )
    assert result is app
    assert app.security is not None
    assert "cors" in app.security


def test_security_setter_accepts_dict():
    app = rivex.Rivex()
    app.security = {"hsts": {"max_age": 60}}
    assert app.security == {"hsts": {"max_age": 60}}


def test_security_setter_clears_with_none():
    app = rivex.Rivex()
    app.security = {"hsts": {"max_age": 60}}
    app.security = None
    assert app.security is None
