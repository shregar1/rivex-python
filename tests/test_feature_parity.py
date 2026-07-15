"""Tests for feature-parity additions (SSE, middleware, caching, pagination, etc.)."""

import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from uuid import UUID

import pytest

from rivex import Rivex, TestClient
from rivex.data.caching import CacheMiddleware, ETagMiddleware
from rivex.middleware.csrf import CSRFMiddleware
from rivex.serialization.encoders import jsonable_encoder
from rivex.middleware.middleware import (
    AccessLogMiddleware,
    MaxBodySizeMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    TrailingSlashMiddleware,
)
from rivex.web.negotiation import best_match, parse_accept
from rivex.data.pagination import CursorPage, paginate
from rivex.core.responses import EventSourceResponse
from rivex.protocols.ws import ConnectionManager

# ── SSE ──


def test_sse_format_event():
    out = EventSourceResponse.format_event("hello")
    assert "data: hello\n" in out


def test_sse_format_event_with_fields():
    out = EventSourceResponse.format_event("hi", event="msg", id="1", retry=5000)
    assert "id: 1\n" in out
    assert "event: msg\n" in out
    assert "retry: 5000\n" in out
    assert "data: hi\n" in out


def test_sse_multiline_data():
    out = EventSourceResponse.format_event("line1\nline2")
    assert "data: line1\n" in out
    assert "data: line2\n" in out


# ── Content negotiation ──


def test_parse_accept_basic():
    result = parse_accept("text/html, application/json;q=0.9")
    assert result[0][0] == "text/html"
    assert result[1][0] == "application/json"
    assert result[1][1] == 0.9


def test_best_match():
    assert best_match("application/json", ["text/html", "application/json"]) == "application/json"


def test_best_match_wildcard():
    assert best_match("*/*", ["application/json"]) == "application/json"


def test_best_match_type_wildcard():
    assert best_match("text/*", ["application/json", "text/plain"]) == "text/plain"


def test_best_match_no_match():
    assert best_match("image/png", ["text/html"]) is None


def test_best_match_empty_header():
    assert best_match("", ["application/json"]) == "application/json"


# ── jsonable_encoder ──


def test_encode_primitives():
    assert jsonable_encoder(42) == 42
    assert jsonable_encoder("hi") == "hi"
    assert jsonable_encoder(None) is None


def test_encode_datetime():
    dt = datetime.datetime(2024, 1, 15, 12, 30)
    assert jsonable_encoder(dt) == dt.isoformat()


def test_encode_uuid():
    u = UUID("12345678-1234-5678-1234-567812345678")
    assert jsonable_encoder(u) == str(u)


def test_encode_decimal():
    assert jsonable_encoder(Decimal("3.14")) == 3.14


def test_encode_enum():
    class Color(Enum):
        RED = "red"

    assert jsonable_encoder(Color.RED) == "red"


def test_encode_path():
    assert jsonable_encoder(Path("/tmp/file.txt")) == "/tmp/file.txt"


def test_encode_dict_exclude_none():
    result = jsonable_encoder({"a": 1, "b": None}, exclude_none=True)
    assert result == {"a": 1}


def test_encode_dict_include():
    result = jsonable_encoder({"a": 1, "b": 2, "c": 3}, include={"a", "c"})
    assert result == {"a": 1, "c": 3}


def test_encode_list():
    assert jsonable_encoder([1, "two", 3.0]) == [1, "two", 3.0]


def test_encode_bytes():
    assert jsonable_encoder(b"hello") == "hello"


def test_encode_timedelta():
    td = datetime.timedelta(hours=1, minutes=30)
    assert jsonable_encoder(td) == 5400.0


# ── Rate limiting ──


def test_rate_limit_allows_requests():
    app = Rivex()
    app.add_middleware(RateLimitMiddleware, rate=10, per=60.0)

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200


def test_rate_limit_blocks_excess():
    app = Rivex()
    app.add_middleware(RateLimitMiddleware, rate=2, per=60.0)

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    client.get("/test")
    client.get("/test")
    resp = client.get("/test")
    assert resp.status_code == 429


# ── Max body size ──


def test_max_body_size_allows_small():
    app = Rivex()
    app.add_middleware(MaxBodySizeMiddleware, max_size=1000)

    @app.post("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.post("/test", json={"small": "data"})
    assert resp.status_code == 200


def test_max_body_size_rejects_large():
    app = Rivex()
    app.add_middleware(MaxBodySizeMiddleware, max_size=10)

    @app.post("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.post("/test", json={"large": "x" * 100})
    assert resp.status_code == 413


# ── Security headers ──


def test_security_headers_added():
    app = Rivex()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"


def test_security_headers_custom():
    app = Rivex()
    app.add_middleware(SecurityHeadersMiddleware, frame_options="SAMEORIGIN", xss_protection=False)

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.headers.get("x-frame-options") == "SAMEORIGIN"
    assert "x-xss-protection" not in resp.headers


# ── Trailing slash ──


def test_trailing_slash_strip_redirects():
    app = Rivex()
    app.add_middleware(TrailingSlashMiddleware, redirect=True, action="strip")

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test/")
    assert resp.status_code == 307


def test_trailing_slash_no_redirect_root():
    app = Rivex()
    app.add_middleware(TrailingSlashMiddleware, redirect=True, action="strip")

    @app.get("/")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200


# ── Access log ──


def test_access_log_doesnt_crash():
    import logging

    app = Rivex()
    app.add_middleware(AccessLogMiddleware, logger_name="test.access")
    logging.getLogger("test.access").setLevel(logging.CRITICAL)

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200


# ── Fallback handler ──


def test_fallback_handler():
    app = Rivex()

    @app.get("/exists")
    async def handler():
        return {"ok": True}

    async def custom_404(request):
        from rivex.core.responses import JSONResponse

        return JSONResponse({"error": "not found", "path": request.path}, status_code=404)

    app.fallback(custom_404)

    client = TestClient(app)
    resp = client.get("/exists")
    assert resp.status_code == 200
    resp = client.get("/missing")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not found"


# ── Route naming + url_for ──


def test_route_naming():
    app = Rivex()

    @app.get("/users/{user_id}", name="get_user")
    async def handler(user_id: int):
        return {"id": user_id}

    assert app.url_for("get_user", user_id=42) == "/users/42"


def test_url_for_missing_name():
    app = Rivex()
    with pytest.raises(ValueError):
        app.url_for("nonexistent")


# ── Route introspection ──


def test_routes_property():
    app = Rivex()

    @app.get("/a")
    async def a():
        return {}

    @app.post("/b")
    async def b():
        return {}

    routes = app.routes
    assert len(routes) == 2
    methods = {r.method for r in routes}
    assert methods == {"GET", "POST"}


# ── Pagination ──


def test_page_basic():
    items = list(range(50))
    page = paginate(items, page=2, size=10)
    assert page.items == list(range(10, 20))
    assert page.total == 50
    assert page.pages == 5
    assert page.has_next is True
    assert page.has_previous is True


def test_page_first():
    page = paginate(list(range(20)), page=1, size=10)
    assert page.has_previous is False
    assert page.has_next is True


def test_page_last():
    page = paginate(list(range(20)), page=2, size=10)
    assert page.has_next is False
    assert page.has_previous is True


def test_page_dict():
    page = paginate([1, 2, 3], page=1, size=10, total=3)
    d = page.dict()
    assert d["items"] == [1, 2, 3]
    assert d["total"] == 3
    assert d["pages"] == 1


def test_cursor_page():
    cp = CursorPage(items=[1, 2], cursor="abc", has_more=True)
    d = cp.dict()
    assert d["cursor"] == "abc"
    assert d["has_more"] is True


# ── ETag middleware ──


def test_etag_added():
    app = Rivex()
    app.add_middleware(ETagMiddleware)

    @app.get("/test")
    async def handler():
        return {"data": "hello"}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert "etag" in resp.headers


def test_etag_304():
    app = Rivex()
    app.add_middleware(ETagMiddleware)

    @app.get("/test")
    async def handler():
        return {"data": "hello"}

    client = TestClient(app)
    resp1 = client.get("/test")
    etag = resp1.headers["etag"]
    resp2 = client.get("/test", headers={"if-none-match": etag})
    assert resp2.status_code == 304


# ── Cache middleware ──


def test_cache_hit():
    app = Rivex()
    app.add_middleware(CacheMiddleware, max_age=300)
    call_count = 0

    @app.get("/test")
    async def handler():
        nonlocal call_count
        call_count += 1
        return {"count": call_count}

    client = TestClient(app)
    resp1 = client.get("/test")
    assert resp1.headers.get("x-cache") == "MISS"
    resp2 = client.get("/test")
    assert resp2.headers.get("x-cache") == "HIT"


# ── CSRF middleware ──


def test_csrf_blocks_post_without_token():
    app = Rivex()
    app.add_middleware(CSRFMiddleware, secret_key="test-secret")

    @app.post("/submit")
    async def submit():
        return {"ok": True}

    client = TestClient(app)
    resp = client.post("/submit")
    assert resp.status_code == 403


def test_csrf_allows_get():
    app = Rivex()
    app.add_middleware(CSRFMiddleware, secret_key="test-secret")

    @app.get("/page")
    async def page():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/page")
    assert resp.status_code == 200


# ── ConnectionManager ──


def test_connection_manager_tracking():
    mgr = ConnectionManager()
    assert mgr.active_connections == 0
    assert mgr.rooms() == []


# ── CLI ──


def test_cli_version():
    import io
    import sys

    from rivex.cli.cli import main

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        main(["version"])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout
    assert "Rivex" in output


def test_cli_routes_bad_path():
    from rivex.cli.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["routes", "nocolon"])
    assert exc_info.value.code == 1
