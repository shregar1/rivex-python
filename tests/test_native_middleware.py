"""Integration tests for the Tier 5 native middleware.

These exercise the Python-side ``add_middleware`` path that mirrors
the Rust implementations in ``rivex-middleware::{security_headers,
request_context, request_timeout, request_validation, audit,
authorization}``. The Rust crate has its own unit tests for the
authoritative behaviour; this file verifies the Python wrappers
behave correctly through the TestClient.
"""

from __future__ import annotations

from rivex import Rivex, Router
from rivex.middleware.middleware_native import (
    AuditLoggerMiddleware,
    AuthorizationMiddleware,
    RequestContextMiddleware,
    RequestTimeoutMiddleware,
    RequestValidationMiddleware,
    SecurityHeadersMiddleware,
)
from rivex.middleware.abstraction import Middleware
from rivex.testing.testing import TestClient


class _ClaimsInjectionMiddleware(Middleware):
    """Tiny test helper that simulates the JWT auth stage by inserting
    ``claims`` into the request extensions before downstream
    middleware sees the request."""

    def __init__(self, claims: dict) -> None:
        self.claims = claims

    async def process(self, request_data, call_next):
        ext = request_data.setdefault("extensions", {})
        ext["claims"] = self.claims
        return await call_next(request_data)


# ── Security headers ────────────────────────────────────────────────


def test_security_headers_baseline():
    app = Rivex()

    @app.get("/x")
    async def x():
        return {"ok": True}

    app.add_middleware(SecurityHeadersMiddleware)

    client = TestClient(app)
    resp = client.get("/x")
    assert resp.status_code == 200
    assert resp.headers["content-security-policy"] == "default-src 'self'"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "strict-transport-security" not in resp.headers  # not emitted here


def test_security_headers_disable_xfo():
    app = Rivex()

    @app.get("/x")
    async def x():
        return {"ok": True}

    app.add_middleware(SecurityHeadersMiddleware, x_frame_options=None)

    client = TestClient(app)
    resp = client.get("/x")
    assert "x-frame-options" not in resp.headers


def test_security_headers_permissions_policy():
    app = Rivex()

    @app.get("/x")
    async def x():
        return {"ok": True}

    app.add_middleware(
        SecurityHeadersMiddleware,
        permissions_policy={"camera": ["self"], "microphone": []},
    )

    client = TestClient(app)
    resp = client.get("/x")
    assert resp.headers["permissions-policy"] == "camera=(self), microphone=()"


# ── Request context ─────────────────────────────────────────────────


def test_request_context_mints_id_and_echoes():
    app = Rivex()

    @app.get("/x")
    async def x():
        return {"ok": True}

    app.add_middleware(RequestContextMiddleware)

    client = TestClient(app)
    resp = client.get("/x")
    assert resp.status_code == 200
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) > 0


def test_request_context_preserves_inbound_id():
    app = Rivex()

    @app.get("/x")
    async def x():
        return {"ok": True}

    app.add_middleware(RequestContextMiddleware)

    client = TestClient(app)
    resp = client.get("/x", headers={"X-Request-Id": "abc-123"})
    assert resp.headers["x-request-id"] == "abc-123"


def test_request_context_custom_headers():
    app = Rivex()

    @app.get("/x")
    async def x():
        return {"ok": True}

    app.add_middleware(
        RequestContextMiddleware,
        request_id_header="X-Correlation-Id",
        tenant_id_header="X-Workspace",
    )

    client = TestClient(app)
    resp = client.get("/x", headers={"X-Correlation-Id": "trace-x"})
    assert resp.headers["x-correlation-id"] == "trace-x"


# ── Request timeout ─────────────────────────────────────────────────


def test_request_timeout_blocks_slow_endpoint():
    import asyncio

    app = Rivex()

    @app.get("/slow")
    async def slow():
        await asyncio.sleep(0.2)
        return {"ok": True}

    app.add_middleware(RequestTimeoutMiddleware, timeout_ms=20)

    client = TestClient(app)
    resp = client.get("/slow")
    assert resp.status_code == 503
    assert resp.text == "Request timed out"


def test_request_timeout_passes_through_fast_endpoint():
    app = Rivex()

    @app.get("/fast")
    async def fast():
        return {"ok": True}

    app.add_middleware(RequestTimeoutMiddleware, timeout_ms=200)

    client = TestClient(app)
    resp = client.get("/fast")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# ── Request validation ──────────────────────────────────────────────


def test_validation_rejects_disallowed_content_type():
    app = Rivex()

    @app.post("/x")
    async def x():
        return {"ok": True}

    app.add_middleware(RequestValidationMiddleware)

    client = TestClient(app)
    resp = client.post("/x", content=b"<x/>", headers={"content-type": "text/xml"})
    assert resp.status_code == 415


def test_validation_enforces_required_headers():
    app = Rivex()

    @app.get("/x")
    async def x():
        return {"ok": True}

    app.add_middleware(RequestValidationMiddleware, required_headers=["X-API-Key"])

    client = TestClient(app)
    resp = client.get("/x")
    assert resp.status_code == 400

    resp = client.get("/x", headers={"X-API-Key": "k"})
    assert resp.status_code == 200


def test_validation_enforces_body_size():
    app = Rivex()

    @app.post("/x")
    async def x():
        return {"ok": True}

    app.add_middleware(RequestValidationMiddleware, max_body_size=4)

    client = TestClient(app)
    resp = client.post(
        "/x",
        content=b'{"too":"big"}',
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 413


# ── Authorization ──────────────────────────────────────────────────


def test_authorization_require_roles_passes():
    app = Rivex()

    @app.get("/admin")
    async def admin():
        return {"ok": True}

    app.add_middleware(
        _ClaimsInjectionMiddleware, claims={"roles": ["admin", "user"]}
    )

    app.add_middleware(
        AuthorizationMiddleware, policy="require_roles", roles=["admin"]
    )

    client = TestClient(app)
    resp = client.get("/admin")
    assert resp.status_code == 200


def test_authorization_require_roles_rejects_missing_role():
    app = Rivex()

    @app.get("/admin")
    async def admin():
        return {"ok": True}

    app.add_middleware(_ClaimsInjectionMiddleware, claims={"roles": ["user"]})

    app.add_middleware(
        AuthorizationMiddleware, policy="require_roles", roles=["admin"]
    )

    client = TestClient(app)
    resp = client.get("/admin")
    assert resp.status_code == 403


def test_authorization_require_any_role():
    app = Rivex()

    @app.get("/ops")
    async def ops():
        return {"ok": True}

    app.add_middleware(_ClaimsInjectionMiddleware, claims={"roles": ["ops"]})

    app.add_middleware(
        AuthorizationMiddleware,
        policy="require_any_role",
        roles=["admin", "ops"],
    )

    client = TestClient(app)
    resp = client.get("/ops")
    assert resp.status_code == 200


def test_authorization_require_scope():
    app = Rivex()

    @app.get("/write")
    async def write():
        return {"ok": True}

    app.add_middleware(
        _ClaimsInjectionMiddleware, claims={"scope": "profile orders:write"}
    )

    app.add_middleware(
        AuthorizationMiddleware,
        policy="require_scope",
        scope="orders:write",
    )

    client = TestClient(app)
    resp = client.get("/write")
    assert resp.status_code == 200


def test_authorization_optional_passes_when_no_claims():
    app = Rivex()

    @app.get("/public")
    async def public():
        return {"ok": True}

    app.add_middleware(
        AuthorizationMiddleware,
        policy="require_roles",
        roles=["admin"],
        required=False,
    )

    client = TestClient(app)
    resp = client.get("/public")
    assert resp.status_code == 200


# ── Router-level integration ────────────────────────────────────────


def test_router_local_middleware_via_group():
    app = Rivex()

    with app.group(prefix="/g", middleware=[SecurityHeadersMiddleware]) as grp:

        @grp.get("/x")
        async def x():
            return {"ok": True}

    client = TestClient(app)
    resp = client.get("/g/x")
    assert resp.headers["x-frame-options"] == "DENY"


def test_router_with_security_headers():
    app = Rivex()
    router = Router(prefix="/api")
    router.add_middleware(SecurityHeadersMiddleware, x_frame_options="SAMEORIGIN")

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    app.include_router(router)

    client = TestClient(app)
    resp = client.get("/api/ping")
    assert resp.headers["x-frame-options"] == "SAMEORIGIN"


# ── Exception handler ─────────────────────────────────────────────


def test_exception_handler_renders_typed_exception():
    from rivex.exceptions import NotFoundException
    from rivex.middleware.middleware_native import ExceptionHandlerMiddleware

    app = Rivex()

    @app.get("/items/{id}")
    async def get_item(id: str):
        if id == "missing":
            raise NotFoundException(f"item {id} gone")
        return {"id": id}

    app.add_middleware(ExceptionHandlerMiddleware)

    client = TestClient(app)
    resp = client.get("/items/ok")
    assert resp.status_code == 200
    assert resp.json() == {"id": "ok"}

    resp = client.get("/items/missing")
    assert resp.status_code == 404
    body = resp.json()
    assert body["status"] == "FAILURE"
    assert body["responseKey"] == "RESOURCE_NOT_FOUND"
    assert body["responseMessage"] == "item missing gone"
    assert body["transactionUrn"].startswith("urn:rivex:")


def test_exception_handler_renders_untyped_exception_as_500():
    """Non-``RivexException`` errors map to a default 500 with the
    framework's legacy ``{"detail": ...}`` body. The Python-side
    handler does NOT envelope-render arbitrary exceptions —
    preserving the framework's behaviour for backward
    compatibility. Typed exceptions do produce envelopes; see
    the previous test."""
    from rivex.middleware.middleware_native import ExceptionHandlerMiddleware

    app = Rivex()

    @app.get("/boom")
    async def boom():
        raise ValueError("something broke")

    app.add_middleware(ExceptionHandlerMiddleware)

    client = TestClient(app)
    resp = client.get("/boom")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal Server Error"}


def test_exception_handler_validation_errors_carried():
    from rivex.exceptions import UnprocessableEntityException, ValidationErrorItem
    from rivex.middleware.middleware_native import ExceptionHandlerMiddleware

    app = Rivex()

    @app.post("/users")
    async def post_user():
        e = UnprocessableEntityException("bad").with_errors(
            [ValidationErrorItem("email", "REQUIRED", "missing")]
        )
        raise e

    app.add_middleware(ExceptionHandlerMiddleware)

    client = TestClient(app)
    resp = client.post("/users", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["responseKey"] == "UNPROCESSABLE_ENTITY"
    assert body["errors"] == [
        {"field": "email", "code": "REQUIRED", "message": "missing"}
    ]


def test_exception_handler_propagate_in_debug():
    from rivex.middleware.middleware_native import ExceptionHandlerMiddleware

    app = Rivex()

    @app.get("/boom")
    async def boom():
        raise ValueError("nope")

    app.add_middleware(ExceptionHandlerMiddleware, propagate_exceptions=True)
    # In TestClient mode, ``propagate_exceptions`` only matters
    # when re-raised inside the framework's exception chain; here
    # we simply assert the middleware accepts the kwarg without
    # errors (the wrapper suppresses the raise inside the loop).
    client = TestClient(app)
    resp = client.get("/boom")
    assert resp.status_code == 500

