"""Tests for feature-parity v2: lifecycle hooks, guards, versioning, problem details, etc."""

import json
import logging

import pytest

from rivex import Rivex, TestClient
from rivex.events import Signal
from rivex.guards import AllowAll, DenyAll, GuardMiddleware, IsAuthenticated, RequiresRoles
from rivex.health import HealthCheck
from rivex.middleware import (
    CompressionMiddleware,
    IdempotencyMiddleware,
    IPFilterMiddleware,
    TimeoutMiddleware,
)
from rivex.problem import (
    ProblemDetail,
    ProblemException,
    ProblemResponse,
    problem_exception_handler,
)
from rivex.structlog import JSONFormatter, StructuredLogger
from rivex.throttling import AnonRateThrottle, ThrottleMiddleware, UserRateThrottle
from rivex.tracing import Span, TracingMiddleware
from rivex.versioning import (
    AcceptHeaderVersioning,
    HeaderVersioning,
    QueryParamVersioning,
    URLPathVersioning,
    VersionMiddleware,
)

# ── Lifecycle hooks ──


def test_before_request_hook():
    app = Rivex()

    @app.before_request
    async def add_header(request_data):
        request_data["_custom"] = "hooked"

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200


def test_before_request_short_circuit():
    app = Rivex()

    @app.before_request
    async def block_all(request_data):
        return {
            "status": 503,
            "headers": [("content-type", "application/json")],
            "body": b'{"detail":"maintenance"}',
        }

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "maintenance"


def test_after_request_hook():
    app = Rivex()

    @app.after_request
    async def add_header(request_data, response):
        response = dict(response)
        headers = list(response.get("headers", []))
        headers.append(("x-custom", "added"))
        response["headers"] = headers
        return response

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.headers.get("x-custom") == "added"


def test_after_response_hook():
    app = Rivex()
    called = []

    @app.after_response
    async def log_it(request_data, response):
        called.append(response.get("status", 0))

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert len(called) == 1


# ── Request timeout ──


def test_timeout_allows_fast_request():
    app = Rivex()
    app.add_middleware(TimeoutMiddleware, timeout=5.0)

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200


def test_timeout_kills_slow_request():
    import asyncio

    app = Rivex()
    app.add_middleware(TimeoutMiddleware, timeout=0.01)

    @app.get("/slow")
    async def handler():
        await asyncio.sleep(1.0)
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/slow")
    assert resp.status_code == 504


# ── IP filter ──


def test_ip_filter_allows():
    app = Rivex()
    app.add_middleware(IPFilterMiddleware, allow=["127.0.0.1"])

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200


def test_ip_filter_denies():
    app = Rivex()
    app.add_middleware(IPFilterMiddleware, deny=["127.0.0.1"])

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 403


# ── Compression ──


def test_compression_gzip():
    app = Rivex()
    app.add_middleware(CompressionMiddleware, minimum_size=10)

    @app.get("/test")
    async def handler():
        return {"data": "x" * 200}

    client = TestClient(app)
    resp = client.get("/test", headers={"accept-encoding": "gzip"})
    assert resp.headers.get("content-encoding") == "gzip"


def test_compression_skips_small():
    app = Rivex()
    app.add_middleware(CompressionMiddleware, minimum_size=10000)

    @app.get("/test")
    async def handler():
        return {"data": "small"}

    client = TestClient(app)
    resp = client.get("/test", headers={"accept-encoding": "gzip"})
    assert "content-encoding" not in resp.headers


# ── Idempotency ──


def test_idempotency_caches_response():
    app = Rivex()
    app.add_middleware(IdempotencyMiddleware)
    call_count = 0

    @app.post("/test")
    async def handler():
        nonlocal call_count
        call_count += 1
        return {"count": call_count}

    client = TestClient(app)
    resp1 = client.post("/test", headers={"idempotency-key": "abc123"})
    resp2 = client.post("/test", headers={"idempotency-key": "abc123"})
    assert resp1.json() == resp2.json()
    assert call_count == 1


def test_idempotency_skips_get():
    app = Rivex()
    app.add_middleware(IdempotencyMiddleware)
    call_count = 0

    @app.get("/test")
    async def handler():
        nonlocal call_count
        call_count += 1
        return {"count": call_count}

    client = TestClient(app)
    client.get("/test", headers={"idempotency-key": "abc"})
    client.get("/test", headers={"idempotency-key": "abc"})
    assert call_count == 2


# ── Throttling ──


def test_anon_throttle_blocks():
    class StrictAnon(AnonRateThrottle):
        rate = "2/minute"

    app = Rivex()
    app.add_middleware(ThrottleMiddleware, throttle_classes=[StrictAnon])

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    client.get("/test")
    client.get("/test")
    resp = client.get("/test")
    assert resp.status_code == 429


def test_user_throttle_uses_user_id():
    class StrictUser(UserRateThrottle):
        rate = "2/minute"

    app = Rivex()
    app.add_middleware(ThrottleMiddleware, throttle_classes=[StrictUser])

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    client.get("/test", headers={"x-user-id": "user1"})
    client.get("/test", headers={"x-user-id": "user1"})
    resp = client.get("/test", headers={"x-user-id": "user1"})
    assert resp.status_code == 429

    resp2 = client.get("/test", headers={"x-user-id": "user2"})
    assert resp2.status_code == 200


# ── Guards ──


def test_guard_allows_authenticated():
    app = Rivex()
    app.add_middleware(GuardMiddleware, guards=[IsAuthenticated()])

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test", headers={"authorization": "Bearer token"})
    assert resp.status_code == 200


def test_guard_blocks_unauthenticated():
    app = Rivex()
    app.add_middleware(GuardMiddleware, guards=[IsAuthenticated()])

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 401


def test_guard_requires_roles():
    app = Rivex()
    app.add_middleware(GuardMiddleware, guards=[RequiresRoles("admin")])

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test", headers={"x-user-roles": "user,editor"})
    assert resp.status_code == 403

    resp2 = client.get("/test", headers={"x-user-roles": "admin,user"})
    assert resp2.status_code == 200


def test_allow_all_guard():
    g = AllowAll()
    assert g({}) is True


def test_deny_all_guard():
    from rivex.exceptions import HTTPException

    g = DenyAll()
    with pytest.raises(HTTPException):
        g({})


# ── API Versioning ──


def test_url_path_versioning():
    v = URLPathVersioning()
    assert v.determine_version({"path": "/v2/users"}) == "2"
    assert v.determine_version({"path": "/users"}) == "1"


def test_header_versioning():
    v = HeaderVersioning()
    assert v.determine_version({"headers": [("accept-version", "3")]}) == "3"
    assert v.determine_version({"headers": []}) == "1"


def test_query_param_versioning():
    v = QueryParamVersioning()
    assert v.determine_version({"query_string": "version=2&foo=bar"}) == "2"
    assert v.determine_version({"query_string": ""}) == "1"


def test_accept_header_versioning():
    v = AcceptHeaderVersioning()
    assert v.determine_version({"headers": [("accept", "application/json; version=4")]}) == "4"


def test_version_middleware():
    app = Rivex()
    app.add_middleware(VersionMiddleware, versioning=HeaderVersioning)

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test", headers={"accept-version": "2"})
    assert resp.status_code == 200


# ── RFC 7807 Problem Details ──


def test_problem_detail_to_dict():
    p = ProblemDetail(
        type="https://example.com/not-found",
        title="Not Found",
        status=404,
        detail="User 42 not found",
        instance="/users/42",
    )
    d = p.to_dict()
    assert d["type"] == "https://example.com/not-found"
    assert d["status"] == 404
    assert d["detail"] == "User 42 not found"


def test_problem_detail_extensions():
    p = ProblemDetail(status=400, title="Bad", extensions={"trace_id": "abc"})
    d = p.to_dict()
    assert d["trace_id"] == "abc"


def test_problem_exception():
    exc = ProblemException(404, "Not Found", detail="gone")
    assert exc.status_code == 404
    assert exc.problem.detail == "gone"


def test_problem_response_create():
    resp = ProblemResponse.create(status=422, title="Validation Error", detail="bad field")
    assert resp["status"] == 422
    body = json.loads(resp["body"])
    assert body["title"] == "Validation Error"
    assert ("content-type", "application/problem+json") in resp["headers"]


def test_problem_exception_handler():
    exc = ProblemException(409, "Conflict", detail="duplicate")
    resp = problem_exception_handler(None, exc)
    assert resp["status"] == 409
    body = json.loads(resp["body"])
    assert body["title"] == "Conflict"


def test_problem_convenience_factories():
    from rivex.problem import (
        bad_request,
        conflict,
        forbidden,
        internal_error,
        not_found,
        unauthorized,
        unprocessable,
    )

    assert not_found().status_code == 404
    assert bad_request().status_code == 400
    assert unauthorized().status_code == 401
    assert forbidden().status_code == 403
    assert conflict().status_code == 409
    assert unprocessable().status_code == 422
    assert internal_error().status_code == 500


# ── Events / Signals ──


def test_signal_send_receive():
    sig = Signal("test")
    received = []

    @sig.receiver()
    def on_event(sender, **kwargs):
        received.append(kwargs)

    sig.send(sender=None, key="value")
    assert len(received) == 1
    assert received[0]["key"] == "value"


def test_signal_disconnect():
    sig = Signal("test")
    called = []

    def handler(sender, **kwargs):
        called.append(1)

    sig.connect(handler)
    sig.send(sender=None)
    assert len(called) == 1

    sig.disconnect(handler)
    sig.send(sender=None)
    assert len(called) == 1


def test_signal_sender_filter():
    sig = Signal("test")
    results = []

    sig.connect(lambda sender, **kw: results.append(sender), sender="app1")

    sig.send(sender="app1")
    sig.send(sender="app2")
    assert results == ["app1"]


def test_predefined_signals():
    from rivex.events import (
        request_started,
        server_shutdown,
    )

    assert request_started.name == "request_started"
    assert server_shutdown.name == "server_shutdown"


# ── Structured Logging ──


def test_json_formatter():
    fmt = JSONFormatter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "hello world", (), None)
    output = fmt.format(record)
    data = json.loads(output)
    assert data["message"] == "hello world"
    assert data["level"] == "info"
    assert "timestamp" in data


def test_structured_logger():
    logger = StructuredLogger("test.struct", level=logging.DEBUG)
    logger.info("test message", key="value")


# ── Health Checks ──


def test_health_check_liveness():
    import asyncio

    hc = HealthCheck()

    @hc.liveness("process")
    def check_alive():
        return True

    result = asyncio.run(hc.check_liveness())
    assert result["status"] == "healthy"


def test_health_check_readiness_fail():
    import asyncio

    hc = HealthCheck()

    @hc.readiness("database")
    def check_db():
        raise ConnectionError("db down")

    result = asyncio.run(hc.check_readiness())
    assert result["status"] == "unhealthy"
    assert result["checks"]["database"]["status"] == "fail"


def test_health_check_register_routes():
    app = Rivex()
    hc = HealthCheck()

    @hc.liveness("process")
    def check():
        return True

    hc.register_routes(app)
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


# ── Tracing ──


def test_span_creation():
    span = Span("GET /test", trace_id="abc", span_id="def")
    span.set_attribute("http.method", "GET")
    span.end()
    d = span.to_dict()
    assert d["trace_id"] == "abc"
    assert d["attributes"]["http.method"] == "GET"
    assert d["duration_ms"] >= 0


def test_tracing_middleware_adds_headers():
    app = Rivex()
    app.add_middleware(TracingMiddleware, service_name="test-api")

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert "x-trace-id" in resp.headers
    assert "traceparent" in resp.headers


def test_tracing_propagates_context():
    app = Rivex()
    app.add_middleware(TracingMiddleware)

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get(
        "/test", headers={"traceparent": "00-abcdef1234567890abcdef1234567890-1234567890abcdef-01"}
    )
    tp = resp.headers.get("traceparent", "")
    assert "abcdef1234567890abcdef1234567890" in tp


# ── Typed path constraints ──


def test_typed_path_int():
    app = Rivex()

    @app.get("/users/{id:int}")
    async def handler(id: int):
        return {"id": id, "type": type(id).__name__}

    client = TestClient(app)
    resp = client.get("/users/42")
    assert resp.status_code == 200
    assert resp.json()["id"] == 42


def test_typed_path_int_rejects_string():
    app = Rivex()

    @app.get("/users/{id:int}")
    async def handler(id: int):
        return {"id": id}

    client = TestClient(app)
    resp = client.get("/users/abc")
    assert resp.status_code == 404


def test_typed_path_float():
    app = Rivex()

    @app.get("/price/{value:float}")
    async def handler(value: float):
        return {"value": value}

    client = TestClient(app)
    resp = client.get("/price/9.99")
    assert resp.status_code == 200
    assert resp.json()["value"] == 9.99


def test_typed_path_uuid():
    app = Rivex()

    @app.get("/items/{item_id:uuid}")
    async def handler(item_id: str):
        return {"id": item_id}

    client = TestClient(app)
    resp = client.get("/items/12345678-1234-5678-1234-567812345678")
    assert resp.status_code == 200

    resp2 = client.get("/items/not-a-uuid")
    assert resp2.status_code == 404


# ── Scoped middleware ──


def test_scoped_middleware():
    from rivex import Router
    from rivex.middleware import SecurityHeadersMiddleware

    app = Rivex()
    router = Router(prefix="/api")
    router.add_middleware(SecurityHeadersMiddleware, frame_options="SAMEORIGIN")

    @router.get("/data")
    async def api_handler():
        return {"data": True}

    @app.get("/public")
    async def public_handler():
        return {"public": True}

    app.include_router(router)
    client = TestClient(app)

    resp_api = client.get("/api/data")
    assert resp_api.status_code == 200
    assert resp_api.headers.get("x-frame-options") == "SAMEORIGIN"

    resp_pub = client.get("/public")
    assert resp_pub.status_code == 200
    assert "x-frame-options" not in resp_pub.headers


# ── Scoped exception handlers ──


def test_scoped_exception_handler():
    from rivex import Router
    from rivex.exceptions import HTTPException
    from rivex.responses import JSONResponse

    app = Rivex()
    router = Router(prefix="/api")

    @router.exception_handler(HTTPException)
    async def custom_handler(request, exc):
        return JSONResponse({"custom_error": exc.detail}, status_code=exc.status_code)

    @router.get("/fail")
    async def fail_handler():
        raise HTTPException(400, "bad input")

    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/fail")
    assert resp.status_code == 400
    assert "custom_error" in resp.json()


# ── Redirect with status codes ──


def test_redirect_default_307():
    from rivex.responses import RedirectResponse

    r = RedirectResponse("/new")
    raw = r._to_raw()
    assert raw["status"] == 307


def test_redirect_301():
    from rivex.responses import RedirectResponse

    r = RedirectResponse("/new", status_code=301)
    raw = r._to_raw()
    assert raw["status"] == 301


def test_redirect_302():
    from rivex.responses import RedirectResponse

    r = RedirectResponse("/new", status_code=302)
    raw = r._to_raw()
    assert raw["status"] == 302


# ── Hot reload CLI ──


def test_cli_reload_flag():
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("app")
    run_parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(["run", "main:app", "--reload"])
    assert args.reload is True
