"""Tests for rivex.native — Rust-speed native handler registration."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from rivex import Rivex
from rivex.native import (
    NativeHandlers,
    health,
    openapi,
    raw_html,
    raw_json,
    raw_response,
    raw_text,
    redirect,
    serve_static,
)


@pytest.fixture
def app():
    return Rivex(docs_url=None, redoc_url=None, landing_page=False, openapi_url=None)


@pytest.fixture
def static_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        (Path(tmpdir) / "index.html").write_text("<h1>Hello</h1>")
        (Path(tmpdir) / "style.css").write_text("body { color: red; }")
        (Path(tmpdir) / "data.json").write_text('{"key": "value"}')
        (Path(tmpdir) / "app.js").write_text("console.log('hi');")
        # Subdirectory
        subdir = Path(tmpdir) / "images"
        subdir.mkdir()
        (subdir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        # Excluded file
        (Path(tmpdir) / "secret.tmp").write_text("temporary")
        yield tmpdir


class TestHealthHandler:
    def test_health_default(self, app):
        health(app)
        # Verify a const route was registered
        const_routes = _get_const_routes(app)
        assert ("GET", "/health") in const_routes

    def test_health_custom_path(self, app):
        health(app, path="/healthz")
        const_routes = _get_const_routes(app)
        assert ("GET", "/healthz") in const_routes

    def test_health_custom_body_dict(self, app):
        health(app, body={"status": "healthy", "version": "1.0"})
        const_routes = _get_const_routes(app)
        route_data = const_routes[("GET", "/health")]
        assert route_data["status"] == 200
        body = json.loads(route_data["body"])
        assert body["status"] == "healthy"
        assert body["version"] == "1.0"

    def test_health_custom_body_string(self, app):
        health(app, body="OK", content_type="text/plain")
        const_routes = _get_const_routes(app)
        route_data = const_routes[("GET", "/health")]
        assert route_data["body"] == b"OK"
        assert route_data["status"] == 200

    def test_health_custom_status(self, app):
        health(app, status=503, body={"status": "down"})
        const_routes = _get_const_routes(app)
        route_data = const_routes[("GET", "/health")]
        assert route_data["status"] == 503

    def test_health_no_cache_header(self, app):
        health(app)
        const_routes = _get_const_routes(app)
        route_data = const_routes[("GET", "/health")]
        headers = dict(route_data["headers"])
        assert headers.get("cache-control") == "no-cache"

    def test_health_via_native_handlers_class(self, app):
        NativeHandlers.health(app, path="/live")
        const_routes = _get_const_routes(app)
        assert ("GET", "/live") in const_routes


class TestRedirectHandler:
    def test_redirect_permanent(self, app):
        redirect(app, "/old", "/new")
        const_routes = _get_const_routes(app)
        assert ("GET", "/old") in const_routes
        route_data = const_routes[("GET", "/old")]
        assert route_data["status"] == 301
        headers = dict(route_data["headers"])
        assert headers["location"] == "/new"

    def test_redirect_temporary(self, app):
        redirect(app, "/temp", "/dest", permanent=False)
        const_routes = _get_const_routes(app)
        route_data = const_routes[("GET", "/temp")]
        assert route_data["status"] == 302

    def test_redirect_external_url(self, app):
        redirect(app, "/go", "https://example.com")
        const_routes = _get_const_routes(app)
        route_data = const_routes[("GET", "/go")]
        headers = dict(route_data["headers"])
        assert headers["location"] == "https://example.com"


class TestOpenAPIHandler:
    def test_openapi_explicit_spec(self, app):
        spec = {"openapi": "3.0.0", "info": {"title": "Test", "version": "1.0"}}
        openapi(app, path="/api.json", spec=spec)
        const_routes = _get_const_routes(app)
        assert ("GET", "/api.json") in const_routes
        route_data = const_routes[("GET", "/api.json")]
        body = json.loads(route_data["body"])
        assert body["openapi"] == "3.0.0"
        assert body["info"]["title"] == "Test"

    def test_openapi_cache_control(self, app):
        spec = {"openapi": "3.0.0"}
        openapi(app, spec=spec, cache_control="public, max-age=86400")
        const_routes = _get_const_routes(app)
        route_data = const_routes[("GET", "/openapi.json")]
        headers = dict(route_data["headers"])
        assert "max-age=86400" in headers["cache-control"]


class TestStaticFilesHandler:
    def test_static_serves_files(self, app, static_dir):
        count = serve_static(app, route="/assets", directory=static_dir)
        # index.html, style.css, data.json, app.js, images/logo.png
        # secret.tmp is NOT excluded (no exclude pattern passed)
        assert count >= 5

        const_routes = _get_const_routes(app)
        assert ("GET", "/assets/style.css") in const_routes
        assert ("GET", "/assets/data.json") in const_routes
        assert ("GET", "/assets/app.js") in const_routes
        assert ("GET", "/assets/images/logo.png") in const_routes

    def test_static_mime_types(self, app, static_dir):
        serve_static(app, route="/s", directory=static_dir)
        const_routes = _get_const_routes(app)

        css_route = const_routes[("GET", "/s/style.css")]
        headers = dict(css_route["headers"])
        assert "text/css" in headers["content-type"]

        json_route = const_routes[("GET", "/s/data.json")]
        headers = dict(json_route["headers"])
        assert "application/json" in headers["content-type"]

    def test_static_index_file(self, app, static_dir):
        serve_static(app, route="/www", directory=static_dir, index_file="index.html")
        const_routes = _get_const_routes(app)

        # The index.html should be accessible at /www/index.html
        assert ("GET", "/www/index.html") in const_routes
        # Also at /www (directory root)
        assert ("GET", "/www") in const_routes
        # And at /www/ (trailing slash)
        assert ("GET", "/www/") in const_routes

    def test_static_exclude_patterns(self, app, static_dir):
        serve_static(
            app, route="/excluded", directory=static_dir, exclude=["*.tmp"]
        )
        const_routes = _get_const_routes(app)
        assert ("GET", "/excluded/secret.tmp") not in const_routes
        # Other files should still be there
        assert ("GET", "/excluded/style.css") in const_routes

    def test_static_max_file_size(self, app, static_dir):
        # Set a very small max size — most files should be skipped
        serve_static(
            app, route="/small", directory=static_dir, max_file_size=10
        )
        # Only files smaller than 10 bytes should be registered
        # style.css is 19 bytes, data.json is 15 bytes — both too big
        # Only very small files pass
        const_routes = _get_const_routes(app)
        for key in const_routes:
            if key[0] == "GET" and key[1].startswith("/small/"):
                route_data = const_routes[key]
                assert len(route_data["body"]) <= 10

    def test_static_cache_control(self, app, static_dir):
        serve_static(
            app, route="/cached", directory=static_dir,
            cache_control="public, max-age=31536000"
        )
        const_routes = _get_const_routes(app)
        css_route = const_routes[("GET", "/cached/style.css")]
        headers = dict(css_route["headers"])
        assert headers["cache-control"] == "public, max-age=31536000"

    def test_static_nonexistent_directory(self, app):
        with pytest.raises(FileNotFoundError):
            serve_static(app, directory="/nonexistent/path/xyz")

    def test_static_file_not_a_directory(self, app, static_dir):
        with pytest.raises(NotADirectoryError):
            serve_static(app, directory=os.path.join(static_dir, "style.css"))


class TestNativeHandlersIntegration:
    def test_multiple_native_handlers_on_same_app(self, app, static_dir):
        NativeHandlers.health(app, "/health")
        NativeHandlers.redirect(app, "/old", "/new")
        NativeHandlers.serve_static(app, "/static", static_dir)

        const_routes = _get_const_routes(app)
        assert ("GET", "/health") in const_routes
        assert ("GET", "/old") in const_routes
        assert ("GET", "/static/style.css") in const_routes

    def test_native_handlers_coexist_with_python_routes(self, app):
        @app.get("/api/data")
        def get_data():
            return {"data": "from python"}

        NativeHandlers.health(app, "/health")

        # Python route should still be registered as a normal route
        assert any(r.path == "/api/data" for r in app._routes)
        # Native route should be a const route
        const_routes = _get_const_routes(app)
        assert ("GET", "/health") in const_routes


class TestRawResponse:
    """Tests for the raw_response / raw_json / raw_text / raw_html helpers."""

    def test_raw_response_basic(self):
        resp = raw_response(b"hello", content_type="text/plain")
        assert resp["_rivex_raw"] is True
        assert resp["status"] == 200
        assert resp["body"] == b"hello"
        assert ("content-type", "text/plain") in resp["headers"]

    def test_raw_response_default_json(self):
        resp = raw_response(b'{"x":1}')
        assert ("content-type", "application/json") in resp["headers"]

    def test_raw_response_custom_status(self):
        resp = raw_response(b"error", status=503, content_type="text/plain")
        assert resp["status"] == 503

    def test_raw_response_custom_headers(self):
        custom = [("x-custom", "yes"), ("content-type", "text/xml")]
        resp = raw_response(b"<xml/>", headers=custom)
        assert resp["headers"] == custom

    def test_raw_response_str_body_encoded(self):
        resp = raw_response("hello world", content_type="text/plain")
        assert resp["body"] == b"hello world"

    def test_raw_json(self):
        resp = raw_json(b'{"id":1}')
        assert resp["_rivex_raw"] is True
        assert resp["status"] == 200
        assert resp["body"] == b'{"id":1}'
        assert ("content-type", "application/json") in resp["headers"]

    def test_raw_text_str(self):
        resp = raw_text("Hello, World!")
        assert resp["body"] == b"Hello, World!"
        assert ("content-type", "text/plain; charset=utf-8") in resp["headers"]

    def test_raw_text_bytes(self):
        resp = raw_text(b"raw bytes")
        assert resp["body"] == b"raw bytes"

    def test_raw_html_str(self):
        resp = raw_html("<h1>Title</h1>")
        assert resp["body"] == b"<h1>Title</h1>"
        assert ("content-type", "text/html; charset=utf-8") in resp["headers"]

    def test_raw_json_via_handler(self, app):
        """Verify raw_json works end-to-end through the dispatch path."""
        try:
            from rivex.di._injection import build_handler_wrapper
        except ImportError:
            from rivex._injection import build_handler_wrapper  # type: ignore[no-redef]
        from rivex_core import json_serialize

        def handler():
            return raw_json(json_serialize({"msg": "ok"}))

        wrapper = build_handler_wrapper(handler, "/test", 200, False, None, None, None)
        import asyncio

        result = asyncio.new_event_loop().run_until_complete(wrapper({}))
        # Should skip normalization — _rivex_raw marker consumed by direct_wrapper
        assert result["body"] == json_serialize({"msg": "ok"})
        assert result["status"] == 200


def _get_const_routes(app):
    """Extract const routes from the app's server as a dict.

    Returns ``{(method, path): {"status": int, "body": bytes, "headers": list}}``.
    """
    server = app._server
    raw = server.get_const_routes()
    result = {}
    for method, path, status, body, headers in raw:
        result[(method, path)] = {"status": status, "body": body, "headers": headers}
    return result
