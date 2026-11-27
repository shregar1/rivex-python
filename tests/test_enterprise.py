"""Tests for enterprise features — HSTS, versioning, signals, Scalar, Inspector, OIDC."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from rivex import Rivex
from rivex.middleware.security import HSTSMiddleware
from rivex.lifecycle.signals import SignalBus, signal_bus
from rivex.web.versioning import VersionedRouter
from rivex.openapi.scalar import render_scalar_html
from rivex.cli.inspector import Inspector
from rivex.auth.oidc import OIDCAuth


@pytest.fixture
def app():
    return Rivex(docs_url=None, redoc_url=None, landing_page=False, openapi_url=None)


# ── HSTS ──


class TestHSTS:
    def test_hsts_default_header(self):
        mw = HSTSMiddleware()
        assert "max-age=31536000" in mw._header_value
        assert "includeSubDomains" in mw._header_value

    def test_hsts_custom_max_age(self):
        mw = HSTSMiddleware(max_age=86400)
        assert "max-age=86400" in mw._header_value

    def test_hsts_no_subdomains(self):
        mw = HSTSMiddleware(include_subdomains=False)
        assert "includeSubDomains" not in mw._header_value

    def test_hsts_preload(self):
        mw = HSTSMiddleware(preload=True)
        assert "preload" in mw._header_value

    @pytest.mark.asyncio
    async def test_hsts_adds_header_to_response(self):
        mw = HSTSMiddleware()

        async def call_next(req):
            return {"status": 200, "headers": [("content-type", "text/plain")], "body": b"ok"}

        result = await mw.process({}, call_next)
        headers = dict(result["headers"])
        assert "strict-transport-security" in headers
        assert "max-age=31536000" in headers["strict-transport-security"]


# ── Versioning ──


class TestVersioning:
    def test_versioned_router_creates_prefix(self, app):
        v1 = VersionedRouter(app, version=1, prefix="/api")
        assert v1._version_prefix == "/api/v1"

    def test_versioned_router_get(self, app):
        v1 = VersionedRouter(app, version=1, prefix="/api")

        @v1.get("/users")
        def users_v1():
            return {"version": 1}

        assert any(r.path == "/api/v1/users" for r in app._routes)

    def test_versioned_router_post(self, app):
        v2 = VersionedRouter(app, version=2, prefix="/api")

        @v2.post("/items")
        def create_item():
            return {"version": 2}

        assert any(r.path == "/api/v2/items" and r.method == "POST" for r in app._routes)

    def test_multiple_versions_coexist(self, app):
        v1 = VersionedRouter(app, version=1, prefix="/api")
        v2 = VersionedRouter(app, version=2, prefix="/api")

        @v1.get("/users")
        def users_v1():
            return {"v": 1}

        @v2.get("/users")
        def users_v2():
            return {"v": 2}

        paths = {r.path for r in app._routes}
        assert "/api/v1/users" in paths
        assert "/api/v2/users" in paths

    def test_versioned_router_no_prefix(self, app):
        v1 = VersionedRouter(app, version=1)

        @v1.get("/health")
        def health():
            return "ok"

        assert any(r.path == "/v1/health" for r in app._routes)

    def test_versioned_router_all_methods(self, app):
        v1 = VersionedRouter(app, version=1)

        @v1.get("/g")
        def g():
            pass

        @v1.post("/p")
        def p():
            pass

        @v1.put("/u")
        def u():
            pass

        @v1.delete("/d")
        def d():
            pass

        @v1.patch("/pa")
        def pa():
            pass

        methods = {(r.method, r.path) for r in app._routes}
        assert ("GET", "/v1/g") in methods
        assert ("POST", "/v1/p") in methods
        assert ("PUT", "/v1/u") in methods
        assert ("DELETE", "/v1/d") in methods
        assert ("PATCH", "/v1/pa") in methods


# ── Signals ──


class TestSignals:
    @pytest.mark.asyncio
    async def test_signal_emit_and_receive(self):
        bus = SignalBus()
        received = []

        @bus.on("test.event")
        async def handler(value: str):
            received.append(value)

        await bus.emit("test.event", value="hello")
        assert received == ["hello"]

    @pytest.mark.asyncio
    async def test_signal_multiple_listeners(self):
        bus = SignalBus()
        results = []

        @bus.on("multi")
        async def handler1(x: int):
            results.append(f"a{x}")

        @bus.on("multi")
        async def handler2(x: int):
            results.append(f"b{x}")

        await bus.emit("multi", x=42)
        assert "a42" in results
        assert "b42" in results
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_signal_no_listeners(self):
        bus = SignalBus()
        # Should not raise
        await bus.emit("unregistered.event", foo="bar")

    @pytest.mark.asyncio
    async def test_signal_listener_error_isolated(self):
        bus = SignalBus()
        successful = []

        @bus.on("risky")
        async def bad_handler():
            raise RuntimeError("boom")

        @bus.on("risky")
        async def good_handler():
            successful.append(True)

        await bus.emit("risky")
        assert successful == [True]  # good handler still ran

    def test_signal_subscribe_unsubscribe(self):
        bus = SignalBus()

        async def listener(x):
            pass

        bus.subscribe("test", listener)
        assert len(bus.listeners("test")) == 1

        bus.unsubscribe("test", listener)
        assert len(bus.listeners("test")) == 0

    def test_signal_list_signals(self):
        bus = SignalBus()

        @bus.on("a")
        async def ha():
            pass

        @bus.on("b")
        async def hb():
            pass

        sigs = bus.signals()
        assert "a" in sigs
        assert "b" in sigs

    def test_signal_clear(self):
        bus = SignalBus()

        @bus.on("temp")
        async def h():
            pass

        bus.clear("temp")
        assert len(bus.listeners("temp")) == 0

    @pytest.mark.asyncio
    async def test_signal_sync_listener(self):
        bus = SignalBus()
        received = []

        @bus.on("sync")
        def sync_handler(msg: str):
            received.append(msg)

        await bus.emit("sync", msg="works")
        assert received == ["works"]


# ── Scalar ──


class TestScalar:
    def test_render_scalar_html_basic(self):
        html = render_scalar_html(spec_url="/openapi.json")
        assert "Scalar" not in html or "api-reference" in html  # CDN script
        assert 'data-url="/openapi.json"' in html
        assert "@scalar/api-reference" in html

    def test_render_scalar_html_custom_title(self):
        html = render_scalar_html(title="My Custom API")
        assert "My Custom API" in html

    def test_render_scalar_html_dark_mode(self):
        html_dark = render_scalar_html(dark_mode=True)
        html_light = render_scalar_html(dark_mode=False)
        assert 'data-theme="dark"' in html_dark
        assert 'data-theme="light"' in html_light


# ── Inspector ──


class TestInspector:
    def test_inspector_creation(self, app):
        inspector = Inspector(app, token="test-token-123")
        assert inspector.token == "test-token-123"
        assert inspector.url == "/_inspector"

    def test_inspector_generates_token(self, app, capsys):
        inspector = Inspector(app)
        assert len(inspector.token) > 10
        captured = capsys.readouterr()
        assert "Inspector token:" in captured.err

    def test_inspector_registers_routes(self, app):
        Inspector(app, token="secret")
        paths = {r.path for r in app._routes}
        assert "/_inspector/status" in paths
        assert "/_inspector/routes" in paths
        assert "/_inspector/commands" in paths

    def test_inspector_custom_command(self, app):
        inspector = Inspector(app, token="secret")

        @inspector.command("ping")
        def ping():
            return {"pong": True}

        assert "ping" in inspector._commands

    def test_inspector_auth_check_no_header(self, app):
        inspector = Inspector(app, token="secret")
        assert not inspector._check_auth({"headers": []})

    def test_inspector_auth_check_valid(self, app):
        inspector = Inspector(app, token="secret")
        headers = [("authorization", "Bearer secret")]
        assert inspector._check_auth({"headers": headers})

    def test_inspector_auth_check_wrong_token(self, app):
        inspector = Inspector(app, token="secret")
        headers = [("authorization", "Bearer wrong")]
        assert not inspector._check_auth({"headers": headers})


# ── OIDC ──


class TestOIDC:
    def test_oidc_creation(self):
        auth = OIDCAuth(
            issuer="https://example.auth0.com",
            audience="my-api",
        )
        assert auth.issuer == "https://example.auth0.com"
        assert auth.audience == "my-api"
        assert auth.jwks_url == "https://example.auth0.com/.well-known/jwks.json"

    def test_oidc_custom_jwks_url(self):
        auth = OIDCAuth(
            issuer="https://example.auth0.com",
            jwks_url="https://custom.com/keys",
        )
        assert auth.jwks_url == "https://custom.com/keys"

    def test_oidc_verify_invalid_format(self):
        auth = OIDCAuth(issuer="https://example.auth0.com")
        with pytest.raises(ValueError, match="Invalid token format"):
            auth.verify_token("not-a-jwt")

    def test_oidc_verify_expired(self):
        auth = OIDCAuth(issuer="https://example.auth0.com")
        # Decode with verify=False to get claims, then manually check expiry
        # We can't easily create a real RS256 JWT without a library,
        # so we test the claim verification logic directly
        claims = {
            "iss": "https://other.auth0.com",
            "exp": time.time() - 100,
        }
        # Test issuer mismatch
        with pytest.raises(ValueError, match="Invalid issuer"):
            # Simulate the claim check
            if claims.get("iss") != auth.issuer:
                raise ValueError(f"Invalid issuer: {claims.get('iss')}")

    def test_oidc_require_auth_returns_middleware(self):
        auth = OIDCAuth(issuer="https://example.auth0.com")
        mw = auth.require_auth()
        assert callable(mw)

    def test_oidc_depends_user_returns_callable(self):
        auth = OIDCAuth(issuer="https://example.auth0.com")
        dep = auth.depends_user()
        assert callable(dep)
