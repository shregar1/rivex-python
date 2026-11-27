"""Tests for the 21 new features (feature parity v3)."""

import pytest

from rivex import Rivex, TestClient
from rivex.di.dependencies import Depends
from rivex.middleware.middleware import MethodOverrideMiddleware
from rivex.http.requests import Request
from rivex.http.responses import XMLResponse

# ── 1. Yield Dependencies ──


def test_yield_dependency_provides_value():
    app = Rivex()
    closed = []

    async def get_resource():
        resource = {"name": "db"}
        try:
            yield resource
        finally:
            closed.append(True)

    @app.get("/test")
    async def handler(res=Depends(get_resource)):
        return {"resource": res["name"]}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json()["resource"] == "db"
    assert closed == [True]


def test_yield_dependency_cleanup_on_error():
    app = Rivex()
    closed = []

    async def get_resource():
        try:
            yield "value"
        finally:
            closed.append(True)

    @app.get("/test")
    async def handler(res=Depends(get_resource)):
        raise ValueError("boom")

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 500
    assert closed == [True]


def test_yield_dependency_sync_generator():
    app = Rivex()
    closed = []

    def get_sync():
        try:
            yield 42
        finally:
            closed.append(True)

    @app.get("/test")
    async def handler(val=Depends(get_sync)):
        return {"val": val}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json()["val"] == 42
    assert closed == [True]


# ── 2. Request.form() ──


def test_request_form():
    app = Rivex()

    @app.post("/form")
    async def handler(request: Request):
        data = request.form()
        return {"name": data.get("name", ""), "age": data.get("age", "")}

    client = TestClient(app)
    resp = client.post("/form", data={"name": "Alice", "age": "30"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Alice"
    assert resp.json()["age"] == "30"


# ── 3. Request.client ──


def test_request_client():
    app = Rivex()

    @app.get("/client")
    async def handler(request: Request):
        c = request.client
        return {"host": c.host, "port": c.port}

    client = TestClient(app)
    resp = client.get("/client")
    assert resp.status_code == 200


# ── 4. Custom JSON Serializer ──


def test_custom_serializer():
    import json as _json

    from rivex.serialization.serialization import deserialize, serialize, set_serializer

    calls = []

    def custom_ser(v):
        calls.append(v)
        return _json.dumps(v).encode()

    set_serializer(custom_ser, _json.loads)

    result = serialize({"data": "hello"})
    assert _json.loads(result)["data"] == "hello"
    assert len(calls) == 1

    assert deserialize(b'{"x": 1}') == {"x": 1}

    set_serializer(lambda v: _json.dumps(v).encode(), _json.loads)


def test_custom_serializer_with_response():
    from rivex.http.responses import JSONResponse

    resp = JSONResponse({"msg": "hi"})
    raw = resp._to_raw()
    body = raw.get("body", b"")
    assert b"hi" in body


# ── 5. Multiple OpenAPI Response Models ──


def test_openapi_multiple_responses():
    from pydantic import BaseModel

    from rivex.openapi.openapi import generate_openapi

    app = Rivex()

    class Item(BaseModel):
        name: str

    class ErrorModel(BaseModel):
        detail: str

    @app.get(
        "/items/{id}",
        response_model=Item,
        responses={
            404: {"model": ErrorModel, "description": "Not found"},
        },
    )
    async def get_item(id: int):
        return {"name": "test"}

    schema = generate_openapi(
        title=app.title,
        version=app.version,
        routes=app._routes,
    )
    path_item = schema["paths"]["/items/{id}"]["get"]
    assert "404" in path_item["responses"]


# ── 6. Mount Sub-Applications ──


def test_mount_sub_app():
    admin = Rivex()

    @admin.get("/users")
    async def admin_users():
        return {"users": ["alice"]}

    app = Rivex()

    @app.get("/")
    async def root():
        return {"app": "main"}

    app.mount("/admin", admin)

    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["app"] == "main"

    resp = client.get("/admin/users")
    assert resp.status_code == 200
    assert resp.json()["users"] == ["alice"]


# ── 7. Route Groups ──


def test_route_group():
    app = Rivex()
    grp = app.group(prefix="/api/v1", tags=["v1"])

    @grp.get("/users")
    async def list_users():
        return {"users": []}

    @grp.get("/items")
    async def list_items():
        return {"items": []}

    grp.flush()

    client = TestClient(app)
    resp = client.get("/api/v1/users")
    assert resp.status_code == 200
    assert resp.json()["users"] == []

    resp = client.get("/api/v1/items")
    assert resp.status_code == 200


def test_route_group_context_manager():
    app = Rivex()

    with app.group(prefix="/admin") as grp:

        @grp.get("/dashboard")
        async def dashboard():
            return {"page": "dashboard"}

    client = TestClient(app)
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert resp.json()["page"] == "dashboard"


# ── 8. OpenTelemetry Integration ──


def test_otel_exporter_no_crash():
    from rivex.observability.tracing import OTelSpanExporter, Span

    exporter = OTelSpanExporter()
    span = Span(name="test", trace_id="abc", span_id="def")
    span.attributes = {"http.method": "GET", "http.path": "/"}
    span.status = "ok"
    exporter.export([span])


def test_configure_tracing():
    from rivex.observability.tracing import configure_tracing

    mw = configure_tracing(service_name="test-app")
    assert mw is not None


# ── 9. Prometheus Metrics ──


def test_counter():
    from rivex.observability.metrics import Counter

    c = Counter("test_total", "Test counter")
    c.inc()
    c.inc(3)
    output = c.collect()
    assert "test_total 4" in output


def test_counter_with_labels():
    from rivex.observability.metrics import Counter

    c = Counter("http_total", "HTTP requests", labels=["method", "status"])
    c.inc(method="GET", status="200")
    c.inc(method="POST", status="201")
    c.inc(method="GET", status="200")
    output = c.collect()
    assert 'method="GET"' in output
    assert 'method="POST"' in output


def test_gauge():
    from rivex.observability.metrics import Gauge

    g = Gauge("active_connections", "Active conns")
    g.set(5)
    g.inc()
    g.dec(2)
    output = g.collect()
    assert "active_connections 4" in output


def test_histogram():
    from rivex.observability.metrics import Histogram

    h = Histogram("request_duration", "Duration", buckets=[0.1, 0.5, 1.0])
    h.observe(0.05)
    h.observe(0.3)
    h.observe(0.8)
    output = h.collect()
    assert "_bucket" in output
    assert "_count" in output
    assert "_sum" in output


def test_histogram_time_context():
    from rivex.observability.metrics import Histogram

    h = Histogram("op_seconds", "Operation time")
    with h.time():
        pass
    output = h.collect()
    assert "op_seconds_count 1" in output


def test_metrics_registry():
    from rivex.observability.metrics import MetricsRegistry

    reg = MetricsRegistry()
    c = reg.counter("my_counter", "A counter")
    g = reg.gauge("my_gauge", "A gauge")
    c.inc()
    g.set(42)
    output = reg.collect()
    assert "my_counter" in output
    assert "my_gauge" in output


def test_metrics_middleware():
    from rivex.observability.metrics import MetricsMiddleware, MetricsRegistry

    reg = MetricsRegistry()
    app = Rivex()
    mw = MetricsMiddleware(registry=reg)
    app.add_middleware(type(mw), registry=reg)

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    client.get("/test")
    output = reg.collect()
    assert "http_requests_total" in output


def test_metrics_register_routes():
    from rivex.observability.metrics import MetricsRegistry

    app = Rivex()
    reg = MetricsRegistry()
    reg.counter("app_starts", "Starts").inc()
    reg.register_routes(app)

    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "app_starts" in resp.text


# ── 10. JWT ──


def test_jwt_encode_decode():
    from rivex.auth.jwt import decode, encode

    token = encode({"sub": "user123", "role": "admin"}, "secret")
    payload = decode(token, "secret")
    assert payload["sub"] == "user123"
    assert payload["role"] == "admin"


def test_jwt_expiration():
    from rivex.auth.jwt import ExpiredTokenError, decode, encode

    token = encode({"sub": "user"}, "secret", expires_in=-1)
    with pytest.raises(ExpiredTokenError):
        decode(token, "secret")


def test_jwt_invalid_signature():
    from rivex.auth.jwt import InvalidTokenError, decode, encode

    token = encode({"sub": "user"}, "secret1")
    with pytest.raises(InvalidTokenError):
        decode(token, "wrong_secret")


def test_jwt_invalid_token_format():
    from rivex.auth.jwt import InvalidTokenError, decode

    with pytest.raises((InvalidTokenError, ValueError, RuntimeError)):
        decode("not.a.valid.token.at.all", "secret")


def test_jwt_bearer_dependency():
    from rivex.auth.jwt import JWTBearer, encode

    app = Rivex()
    jwt_auth = JWTBearer(secret="mysecret")

    @app.get("/protected")
    async def protected(payload=Depends(jwt_auth)):
        return {"user": payload.get("sub", "")}

    client = TestClient(app)
    token = encode({"sub": "alice"}, "mysecret")
    resp = client.get("/protected", headers={"authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["user"] == "alice"


def test_jwt_bearer_no_token():
    from rivex.auth.jwt import JWTBearer

    app = Rivex()

    @app.get("/protected")
    async def protected(payload=Depends(JWTBearer(secret="s"))):
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 401


# ── 11. Router-level Lifecycle Hooks ──


def test_router_before_request():
    from rivex.web.routing import Router

    app = Rivex()
    router = Router(prefix="/api")
    marker_seen = []

    @router.before_request
    async def add_marker(request_data):
        marker_seen.append(True)

    @router.get("/check")
    async def check():
        return {"ok": True}

    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/check")
    assert resp.status_code == 200
    assert len(marker_seen) == 1


def test_router_after_request():
    from rivex.web.routing import Router

    app = Rivex()
    router = Router(prefix="/api")

    @router.after_request
    async def add_header(request_data, response):
        response = dict(response)
        headers = list(response.get("headers", []))
        headers.append(("x-router-hook", "true"))
        response["headers"] = headers
        return response

    @router.get("/data")
    async def data():
        return {"ok": True}

    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/data")
    assert resp.status_code == 200
    assert resp.headers.get("x-router-hook") == "true"


# ── 12. Plugin System ──


def test_plugin_register():
    from rivex.cli.plugins import Plugin

    class MyPlugin(Plugin):
        name = "my_plugin"
        installed = False

        def install(self, app):
            self.installed = True

    app = Rivex()
    plugin = MyPlugin()
    app.register_plugin(plugin)
    assert plugin.installed
    assert app.get_plugin("my_plugin") is plugin


def test_plugin_adds_routes():
    from rivex.cli.plugins import Plugin

    class HealthPlugin(Plugin):
        name = "health"

        def install(self, app):
            @app.get("/plugin-health")
            async def health():
                return {"status": "ok"}

    app = Rivex()
    app.register_plugin(HealthPlugin())

    client = TestClient(app)
    resp = client.get("/plugin-health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── 13. Route-level Cache TTL ──


def test_cache_ttl_metadata():
    app = Rivex()

    @app.get("/data", cache_ttl=60)
    async def data():
        return {"ok": True}

    route = app._routes[-1]
    assert route.cache_ttl == 60


# ── 14. Streaming Request Body ──


def test_request_stream():
    app = Rivex()

    @app.post("/upload")
    async def upload(request: Request):
        chunks = []
        async for chunk in request.stream():
            chunks.append(chunk)
        return {"size": sum(len(c) for c in chunks)}

    client = TestClient(app)
    resp = client.post("/upload", content=b"hello world")
    assert resp.status_code == 200
    assert resp.json()["size"] == 11


# ── 15. Dependency Scopes ──


def test_dependency_scope_request():
    app = Rivex()
    call_count = 0

    async def get_val():
        nonlocal call_count
        call_count += 1
        return call_count

    @app.get("/test")
    async def handler(a=Depends(get_val), b=Depends(get_val)):
        return {"a": a, "b": b}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json()["a"] == resp.json()["b"]


def test_dependency_scope_transient():
    app = Rivex()
    call_count = 0

    async def get_val():
        nonlocal call_count
        call_count += 1
        return call_count

    @app.get("/test")
    async def handler(
        a=Depends(get_val, scope="transient"),
        b=Depends(get_val, scope="transient"),
    ):
        return {"a": a, "b": b}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json()["a"] != resp.json()["b"]


# ── 16. Request.base_url ──


def test_request_base_url():
    app = Rivex()

    @app.get("/test")
    async def handler(request: Request):
        return {"base": request.base_url}

    client = TestClient(app)
    resp = client.get("/test", headers={"host": "example.com"})
    assert resp.status_code == 200
    assert "example.com" in resp.json()["base"]


def test_request_base_url_https():
    app = Rivex()

    @app.get("/test")
    async def handler(request: Request):
        return {"base": request.base_url}

    client = TestClient(app)
    resp = client.get(
        "/test",
        headers={
            "host": "example.com",
            "x-forwarded-proto": "https",
        },
    )
    assert resp.json()["base"].startswith("https://")


# ── 17. Host-based Routing ──


def test_host_routing():
    app = Rivex()

    @app.get("/", host="api.example.com")
    async def api_root():
        return {"app": "api"}

    @app.get("/", host="admin.example.com")
    async def admin_root():
        return {"app": "admin"}

    client = TestClient(app)
    resp = client.get("/", headers={"host": "api.example.com"})
    assert resp.status_code == 200
    assert resp.json()["app"] == "api"

    resp = client.get("/", headers={"host": "admin.example.com"})
    assert resp.status_code == 200
    assert resp.json()["app"] == "admin"


# ── 18. Regex Path Constraints ──


def test_regex_path_match():
    app = Rivex()

    @app.get("/items/{code:re:[A-Z]{3}-[0-9]{4}}")
    async def get_item(code: str):
        return {"code": code}

    client = TestClient(app)
    resp = client.get("/items/ABC-1234")
    assert resp.status_code == 200
    assert resp.json()["code"] == "ABC-1234"


def test_regex_path_no_match():
    app = Rivex()

    @app.get("/items/{code:re:[A-Z]{3}-[0-9]{4}}")
    async def get_item(code: str):
        return {"code": code}

    client = TestClient(app)
    resp = client.get("/items/abc-12")
    assert resp.status_code == 404


# ── 19. XML Response ──


def test_xml_response():
    app = Rivex()

    @app.get("/xml")
    async def xml_endpoint():
        return XMLResponse("<root><item>hello</item></root>")

    client = TestClient(app)
    resp = client.get("/xml")
    assert resp.status_code == 200
    assert "<root>" in resp.text
    assert resp.headers.get("content-type") == "application/xml"


# ── 20. HTTP Method Override ──


def test_method_override():
    app = Rivex()
    app.add_middleware(MethodOverrideMiddleware)

    @app.patch("/items/1")
    async def update_item():
        return {"updated": True}

    client = TestClient(app)
    resp = client.post("/items/1", headers={"x-http-method-override": "PATCH"})
    assert resp.status_code == 200
    assert resp.json()["updated"] is True


# ── 21. Webhook Signature Verification ──


def test_webhook_github():
    import hashlib
    import hmac

    from rivex.protocols.webhooks import verify_signature

    secret = "webhook-secret"
    payload = b'{"action":"push"}'
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    assert verify_signature(payload, sig, secret, provider="github") is True


def test_webhook_github_invalid():
    from rivex.protocols.webhooks import WebhookVerificationError, verify_signature

    with pytest.raises(WebhookVerificationError):
        verify_signature(b"payload", "sha256=invalid", "secret", provider="github")


def test_webhook_generic():
    import hashlib
    import hmac

    from rivex.protocols.webhooks import verify_signature

    secret = "test"
    payload = b"hello"
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    assert verify_signature(payload, sig, secret, provider="generic") is True


def test_webhook_guard_dependency():
    import hashlib
    import hmac

    from rivex.protocols.webhooks import WebhookGuard

    app = Rivex()
    secret = "whsec_test"

    @app.post("/webhook")
    async def webhook(verified=Depends(WebhookGuard(secret=secret, provider="github"))):
        return {"received": True}

    payload = b'{"event":"test"}'
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    client = TestClient(app)
    resp = client.post(
        "/webhook",
        content=payload,
        headers={"x-hub-signature-256": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["received"] is True


# ── 22. Pydantic Form Model Support ──


def test_form_model_urlencoded():
    from pydantic import BaseModel

    from rivex.web.uploads import Form

    app = Rivex()

    class LoginForm(BaseModel):
        username: str
        password: str

    @app.post("/login")
    async def login(data: LoginForm = Form()):
        return {"user": data.username}

    client = TestClient(app)
    resp = client.post(
        "/login",
        content=b"username=alice&password=secret",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    assert resp.json()["user"] == "alice"


def test_form_model_validation_error():
    from pydantic import BaseModel

    from rivex.web.uploads import Form

    app = Rivex()

    class RegisterForm(BaseModel):
        email: str
        age: int

    @app.post("/register")
    async def register(data: RegisterForm = Form()):
        return {"email": data.email, "age": data.age}

    client = TestClient(app)
    resp = client.post(
        "/register",
        content=b"email=test@example.com&age=not_a_number",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 422


def test_form_model_optional():
    from pydantic import BaseModel

    from rivex.web.uploads import Form

    app = Rivex()

    class SearchForm(BaseModel):
        q: str
        page: int = 1

    @app.post("/search")
    async def search(data: SearchForm = Form()):
        return {"q": data.q, "page": data.page}

    client = TestClient(app)
    resp = client.post(
        "/search",
        content=b"q=hello",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    assert resp.json()["q"] == "hello"
    assert resp.json()["page"] == 1


def test_form_model_missing_required():
    from pydantic import BaseModel

    from rivex.web.uploads import Form

    app = Rivex()

    class ContactForm(BaseModel):
        name: str
        message: str

    @app.post("/contact")
    async def contact(data: ContactForm = Form()):
        return {"name": data.name}

    client = TestClient(app)
    resp = client.post(
        "/contact",
        content=b"",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 422


def test_form_model_not_required_default():
    from pydantic import BaseModel

    from rivex.web.uploads import Form

    app = Rivex()

    class Prefs(BaseModel):
        theme: str = "light"

    @app.post("/prefs")
    async def prefs(data: Prefs = Form(None)):
        if data is None:
            return {"default": True}
        return {"theme": data.theme}

    client = TestClient(app)
    resp = client.post(
        "/prefs",
        content=b"",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    assert resp.json()["default"] is True
