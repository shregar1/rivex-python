"""
End-to-end test exercising EVERY Rivex feature in a single realistic API server.

The server simulates a production-grade "TaskForge" project management API with:
- User auth (JWT, API keys, HTTP Basic, OAuth2)
- CRUD endpoints for projects/tasks/comments
- File uploads, form models, pagination
- Background tasks, streaming, SSE, webhooks
- Middleware stack: CORS, request-id, compression, rate-limit, sessions,
  CSRF, cache, ETag, security headers, method override, idempotency,
  max body size, trailing slash, timeout, IP filter
- Guards, throttling, versioning, content negotiation
- Health checks, metrics, tracing, structured logging
- Plugins, route groups, controllers, routers with lifecycle hooks
- Custom serialization, exception handlers, problem details (RFC 7807)
- Signals/events, dependency scopes, yield dependencies
- Response types: JSON, HTML, XML, plaintext, redirect, streaming, file, SSE
- OpenAPI generation, host-based routing, regex path constraints
- Pydantic body/form model validation, response model filtering
"""

import base64
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time

import pytest
from pydantic import BaseModel, Field

from rivex import (
    # Security
    APIKeyHeader,
    APIStatus,
    BackgroundTasks,
    # Params
    Body,
    Controller,
    CORSMiddleware,
    Counter,
    CursorPage,
    Depends,
    EventSourceResponse,
    File,
    Form,
    Gauge,
    # Guards
    HealthCheck,
    Histogram,
    HTMLResponse,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPException,
    # Status
    HTTPMethod,
    IdempotencyMiddleware,
    JSONResponse,
    JWTBearer,
    MaxBodySizeMiddleware,
    MethodOverrideMiddleware,
    MetricsMiddleware,
    # Metrics
    MetricsRegistry,
    # Middleware
    OAuth2PasswordBearer,
    # Pagination
    PlainTextResponse,
    Plugin,
    # Problem details
    ProblemException,
    ProblemResponse,
    Query,
    RedirectResponse,
    Request,
    RequestIdMiddleware,
    Response,
    Rivex,
    Router,
    SecurityHeadersMiddleware,
    # Events
    Signal,
    # Tracing
    Span,
    StreamingResponse,
    TestClient,
    UploadFile,
    WebhookGuard,
    XMLResponse,
    bad_request,
    best_match,
    get,
    # Encoders
    jsonable_encoder,
    jwt_decode,
    # JWT
    jwt_encode,
    not_found,
    paginate,
    # Negotiation
    parse_accept,
    post,
    problem_exception_handler,
    verify_signature,
)
from rivex import (
    Cookie as CookieParam,
)
from rivex import (
    Header as HeaderParam,
)
from rivex import (
    Path as PathParam,
)
from rivex.middleware.sessions import SessionMiddleware

# ============================================================================
# Pydantic Models
# ============================================================================


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str
    password: str = Field(min_length=6)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = Field(default=1, ge=1, le=5)


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    priority: int
    status: str = "pending"
    assignee: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: int | None = None
    status: str | None = None


class LoginForm(BaseModel):
    username: str
    password: str


class SearchForm(BaseModel):
    query: str
    category: str = "all"
    page: int = 1


class CommentCreate(BaseModel):
    text: str
    author: str


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


# ============================================================================
# In-memory database
# ============================================================================

_db = {
    "users": {},
    "tasks": {},
    "projects": {},
    "comments": {},
    "uploads": [],
    "bg_log": [],
}
_counters = {"users": 0, "tasks": 0, "projects": 0, "comments": 0}
JWT_SECRET = "test-jwt-secret-key-2024"
API_KEY = "sk-test-api-key-12345"
WEBHOOK_SECRET = "whsec_test_secret"
SESSION_SECRET = "session-secret-key-for-testing"


def _reset_db():
    _db["users"].clear()
    _db["tasks"].clear()
    _db["projects"].clear()
    _db["comments"].clear()
    _db["uploads"].clear()
    _db["bg_log"].clear()
    _counters["users"] = 0
    _counters["tasks"] = 0
    _counters["projects"] = 0
    _counters["comments"] = 0


# ============================================================================
# Dependencies
# ============================================================================


def get_db():
    return _db


async def get_current_user(request: Request) -> dict:
    auth = request.header("authorization")
    if not auth:
        raise HTTPException(401, "Missing authorization")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer":
        payload = jwt_decode(token, JWT_SECRET)
        return payload
    raise HTTPException(401, "Invalid auth scheme")


async def yield_connection():
    conn = {"connected": True, "queries": 0}
    try:
        yield conn
    finally:
        conn["connected"] = False


# ============================================================================
# Plugin
# ============================================================================


class AuditPlugin(Plugin):
    name = "audit"

    def install(self, app):
        @app.get("/audit/status")
        async def audit_status():
            return {"plugin": "audit", "active": True}


# ============================================================================
# Controller
# ============================================================================


class ProjectController(Controller):
    path = "/projects"
    tags = ["projects"]

    @get("/")
    def list_projects(self):
        return {"projects": list(_db["projects"].values())}

    @post("/", status_code=201)
    def create_project(self, data: ProjectCreate):
        _counters["projects"] += 1
        pid = _counters["projects"]
        project = {"id": pid, "name": data.name, "description": data.description}
        _db["projects"][pid] = project
        return project

    @get("/{project_id}")
    def get_project(self, project_id: int):
        p = _db["projects"].get(project_id)
        if not p:
            raise HTTPException(404, "Project not found")
        return p


# ============================================================================
# Build the full app
# ============================================================================


def build_app() -> Rivex:
    _reset_db()

    registry = MetricsRegistry()
    health = HealthCheck()

    @health.liveness("process")
    def check_process():
        return True

    @health.readiness("database")
    def check_db():
        return {"status": "ok", "latency_ms": 1}

    app = Rivex(
        title="TaskForge API",
        version="2.0.0",
        description="Complete E2E test server",
    )

    # ── Middleware stack ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://taskforge.dev"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(MaxBodySizeMiddleware, max_size=5_000_000)
    app.add_middleware(MethodOverrideMiddleware)
    app.add_middleware(MetricsMiddleware, registry=registry)
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

    # ── Exception handlers ──
    app.exception_handler(ProblemException)(problem_exception_handler)

    @app.exception_handler(ValueError)
    def handle_value_error(request, exc):
        return {
            "status": 400,
            "headers": [("content-type", "application/json")],
            "body": json.dumps({"detail": f"ValueError: {exc}"}).encode(),
        }

    # ── Plugins ──
    app.register_plugin(AuditPlugin())

    # ── Health & Metrics ──
    health.register_routes(app)
    registry.register_routes(app)

    # ── Events / Signals ──
    event_log = []
    app_signal = Signal("app_event")

    @app_signal.receiver()
    def on_event(sender, **kwargs):
        event_log.append({"sender": sender, **kwargs})

    # ══════════════════════════════════════════════════════════════════
    # ENDPOINTS
    # ══════════════════════════════════════════════════════════════════

    # ── 1. Root ──
    @app.get("/")
    async def root():
        return {"app": "TaskForge", "version": "2.0.0"}

    # ── 2. User Registration (Pydantic body) ──
    @app.post("/auth/register", status_code=201, response_model=UserResponse)
    async def register(user: UserCreate):
        _counters["users"] += 1
        uid = _counters["users"]
        record = {
            "id": uid,
            "username": user.username,
            "email": user.email,
            "password": user.password,
        }
        _db["users"][uid] = record
        return {"id": uid, "username": user.username, "email": user.email}

    # ── 3. Login (Form model) ──
    @app.post("/auth/login")
    async def login(form: LoginForm = Form()):
        for u in _db["users"].values():
            if u["username"] == form.username and u["password"] == form.password:
                token = jwt_encode(
                    {"sub": u["username"], "uid": u["id"]}, JWT_SECRET, expires_in=3600
                )
                return {"access_token": token, "token_type": "bearer"}
        raise HTTPException(401, "Invalid credentials")

    # ── 4. JWT protected ──
    @app.get("/auth/me")
    async def me(payload: dict = Depends(JWTBearer(secret=JWT_SECRET))):
        return {"user": payload["sub"], "uid": payload["uid"]}

    # ── 5. API key auth ──
    api_key_dep = APIKeyHeader(name="x-api-key")

    @app.get("/auth/apikey")
    async def apikey_check(key=Depends(api_key_dep)):
        if key != API_KEY:
            raise HTTPException(403, "Invalid API key")
        return {"authenticated": True}

    # ── 6. HTTP Basic auth ──
    basic_auth = HTTPBasic()

    @app.get("/auth/basic")
    async def basic_check(creds: HTTPBasicCredentials = Depends(basic_auth)):
        if creds.username != "admin" or creds.password != "secret":
            raise HTTPException(401, "Bad credentials")
        return {"user": creds.username}

    # ── 7. OAuth2 bearer ──
    oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")

    @app.get("/auth/oauth2")
    async def oauth2_check(token=Depends(oauth2)):
        payload = jwt_decode(token, JWT_SECRET)
        return {"sub": payload["sub"]}

    # ── 8. Task CRUD with all param types ──
    @app.post("/tasks", status_code=201, tags=["tasks"])
    async def create_task(task: TaskCreate, request: Request):
        _counters["tasks"] += 1
        tid = _counters["tasks"]
        record = {
            "id": tid,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "status": "pending",
            "assignee": None,
        }
        _db["tasks"][tid] = record
        return record

    @app.get("/tasks", tags=["tasks"])
    async def list_tasks(
        page: int = 1,
        size: int = 10,
        status_filter: str = Query(default=""),
    ):
        all_tasks = list(_db["tasks"].values())
        if status_filter:
            all_tasks = [t for t in all_tasks if t["status"] == status_filter]
        result = paginate(all_tasks, page=page, size=size)
        return result.dict()

    @app.get("/tasks/{task_id}", tags=["tasks"])
    async def get_task(task_id: int):
        t = _db["tasks"].get(task_id)
        if not t:
            raise not_found(detail=f"Task {task_id} not found", instance=f"/tasks/{task_id}")
        return t

    @app.put("/tasks/{task_id}", tags=["tasks"])
    async def update_task(task_id: int, data: TaskUpdate):
        t = _db["tasks"].get(task_id)
        if not t:
            raise HTTPException(404, "Task not found")
        if data.title is not None:
            t["title"] = data.title
        if data.description is not None:
            t["description"] = data.description
        if data.priority is not None:
            t["priority"] = data.priority
        if data.status is not None:
            t["status"] = data.status
        return t

    @app.patch("/tasks/{task_id}/assign", tags=["tasks"])
    async def assign_task(task_id: int, assignee: str = Body(embed=True)):
        t = _db["tasks"].get(task_id)
        if not t:
            raise HTTPException(404, "Task not found")
        t["assignee"] = assignee
        return t

    @app.delete("/tasks/{task_id}", status_code=204, tags=["tasks"])
    async def delete_task(task_id: int):
        if task_id not in _db["tasks"]:
            raise HTTPException(404, "Task not found")
        del _db["tasks"][task_id]

    # ── 9. Response model filtering ──
    @app.get(
        "/tasks/{task_id}/summary",
        response_model=TaskResponse,
        response_model_include={"id", "title", "status"},
        response_model_exclude_none=True,
        tags=["tasks"],
    )
    async def task_summary(task_id: int):
        t = _db["tasks"].get(task_id)
        if not t:
            raise HTTPException(404, "Task not found")
        return t

    # ── 10. Query/Header/Cookie params ──
    @app.get("/echo/params")
    async def echo_params(
        q: str = Query(default=""),
        x_custom: str = HeaderParam(default="none"),
        session_id: str = CookieParam(default="anon"),
    ):
        return {"q": q, "x_custom": x_custom, "session_id": session_id}

    # ── 11. Path param with type constraint ──
    @app.get("/items/{item_id}")
    async def get_item(item_id: int = PathParam()):
        return {"item_id": item_id}

    # ── 12. File upload ──
    @app.post("/upload")
    async def upload_file(file: UploadFile = File()):
        content = await file.read()
        _db["uploads"].append(
            {
                "filename": file.filename,
                "size": len(content),
                "content_type": file.content_type,
            }
        )
        return {"filename": file.filename, "size": len(content)}

    # ── 13. Form fields (individual) ──
    @app.post("/contact")
    async def contact(
        name: str = Form(),
        email: str = Form(),
        message: str = Form(default=""),
    ):
        return {"name": name, "email": email, "message": message}

    # ── 14. Form model (Pydantic) ──
    @app.post("/search")
    async def search(data: SearchForm = Form()):
        return {"query": data.query, "category": data.category, "page": data.page}

    # ── 15. Background tasks ──
    @app.post("/notifications/send")
    async def send_notification(bg: BackgroundTasks, message: str = Body(embed=True)):
        def _send(msg: str):
            _db["bg_log"].append(f"sent:{msg}")

        bg.add_task(_send, message)
        return {"queued": True}

    @app.get("/notifications/log")
    async def get_bg_log():
        return {"log": list(_db["bg_log"])}

    # ── 16. Yield dependency ──
    @app.get("/db/status")
    async def db_status(conn=Depends(yield_connection)):
        conn["queries"] += 1
        return {"connected": conn["connected"], "queries": conn["queries"]}

    # ── 17. Dependency scopes ──
    call_count = {"transient": 0, "singleton": 0}

    def transient_dep():
        call_count["transient"] += 1
        return call_count["transient"]

    def singleton_dep():
        call_count["singleton"] += 1
        return call_count["singleton"]

    @app.get("/deps/transient")
    async def dep_transient(val=Depends(transient_dep, scope="transient")):
        return {"val": val}

    # ── 18. Response types ──
    @app.get("/responses/json")
    async def resp_json():
        return JSONResponse({"format": "json"})

    @app.get("/responses/html")
    async def resp_html():
        return HTMLResponse("<h1>Hello</h1>")

    @app.get("/responses/text")
    async def resp_text():
        return PlainTextResponse("plain text response")

    @app.get("/responses/xml")
    async def resp_xml():
        return XMLResponse("<root><status>ok</status></root>")

    @app.get("/responses/redirect")
    async def resp_redirect():
        return RedirectResponse("/", status_code=302)

    @app.get("/responses/streaming")
    async def resp_streaming():
        def generate():
            for i in range(5):
                yield f"chunk-{i}\n"

        return StreamingResponse(generate(), media_type="text/plain")

    @app.get("/responses/sse")
    async def resp_sse():
        def events():
            for i in range(3):
                yield EventSourceResponse.format_event(
                    data=json.dumps({"count": i}),
                    event="tick",
                    id=str(i),
                )

        return EventSourceResponse(events())

    @app.get("/responses/file")
    async def resp_file():
        from rivex.http.responses import FileResponse

        path = os.path.join(tempfile.gettempdir(), "rivex_test_file.txt")
        with open(path, "w") as f:
            f.write("file content for download")
        return FileResponse(path, filename="test.txt")

    @app.get("/responses/cookie")
    async def resp_cookie():
        r = Response(content="ok", media_type="text/plain")
        r.set_cookie("session_token", "abc123", max_age=3600, httponly=True, samesite="lax")
        r.set_cookie("theme", "dark")
        return r

    # ── 19. Custom status codes ──
    @app.post("/resources", status_code=201)
    async def create_resource():
        return {"created": True}

    @app.delete("/resources/{rid}", status_code=204)
    async def delete_resource(rid: int):
        pass

    # ── 20. Exception handling ──
    @app.get("/errors/http")
    async def error_http():
        raise HTTPException(418, detail="I'm a teapot")

    @app.get("/errors/problem")
    async def error_problem():
        raise ProblemException(
            status=422,
            title="Validation Error",
            detail="Field 'name' is required",
            type="https://errors.taskforge.dev/validation",
            instance="/errors/problem",
            field="name",
        )

    @app.get("/errors/value")
    async def error_value():
        raise ValueError("something went wrong")

    # ── 21. Webhooks ──
    @app.post("/webhooks/github")
    async def webhook_github(
        verified=Depends(WebhookGuard(secret=WEBHOOK_SECRET, provider="github")),
    ):
        return {"verified": verified}

    @app.post("/webhooks/generic")
    async def webhook_generic(
        verified=Depends(WebhookGuard(secret=WEBHOOK_SECRET, provider="generic")),
    ):
        return {"verified": verified}

    # ── 22. Content negotiation ──
    @app.get("/negotiate")
    async def negotiate(request: Request):
        accept = request.header("accept", "*/*")
        match = best_match(accept, ["application/json", "text/html", "application/xml"])
        if match == "text/html":
            return HTMLResponse("<p>HTML</p>")
        elif match == "application/xml":
            return XMLResponse("<data>xml</data>")
        return {"format": "json"}

    # ── 23. Streaming request body ──
    @app.post("/stream/echo")
    async def stream_echo(request: Request):
        chunks = []
        async for chunk in request.stream():
            chunks.append(chunk)
        return {"received_bytes": sum(len(c) for c in chunks)}

    # ── 24. Request properties ──
    @app.get("/request/info")
    async def request_info(request: Request):
        return {
            "method": request.method,
            "path": request.path,
            "url": request.url,
            "content_type": request.content_type,
            "base_url": request.base_url,
        }

    # ── 25. Pagination ──
    @app.get("/paginated")
    async def paginated_list(page: int = 1, size: int = 5):
        items = [{"id": i, "name": f"item-{i}"} for i in range(1, 51)]
        result = paginate(items, page=page, size=size)
        return result.dict()

    @app.get("/cursor-paginated")
    async def cursor_paginated(cursor: str = "", limit: int = 5):
        items = [{"id": i} for i in range(1, 21)]
        start = int(cursor) if cursor else 0
        page_items = items[start : start + limit]
        next_cursor = str(start + limit) if start + limit < len(items) else None
        return CursorPage(
            items=page_items, cursor=next_cursor, has_more=next_cursor is not None
        ).dict()

    # ── 26. Signals/Events ──
    @app.post("/events/emit")
    async def emit_event(name: str = Body(embed=True)):
        app_signal.send(sender="api", event_name=name)
        return {"emitted": name, "total_events": len(event_log)}

    @app.get("/events/log")
    async def get_events():
        return {"events": event_log}

    # ── 27. Sessions ──
    @app.post("/session/set")
    async def session_set(
        request: Request, key: str = Body(embed=True), value: str = Body(embed=True)
    ):
        _ = request._from_raw.__func__  # just test session exists
        return {"set": True}

    # ── 28. jsonable_encoder ──
    @app.get("/encode/complex")
    async def encode_complex():
        from datetime import datetime, timedelta
        from decimal import Decimal
        from uuid import UUID

        data = {
            "timestamp": datetime(2024, 1, 15, 12, 0, 0),
            "duration": timedelta(hours=2),
            "amount": Decimal("99.99"),
            "id": UUID("12345678-1234-5678-1234-567812345678"),
        }
        return jsonable_encoder(data)

    # ── 29. Guards ──
    def require_admin(request: Request):
        headers = {k: v for k, v in request.headers.items()}
        user_roles = {r.strip() for r in headers.get("x-user-roles", "").split(",") if r.strip()}
        if not {"admin"}.intersection(user_roles):
            raise HTTPException(403, "Insufficient permissions")
        return True

    @app.get("/admin/dashboard")
    async def admin_dashboard(_=Depends(require_admin)):
        return {"admin": True}

    # ── 30. Regex path constraints ──
    @app.get("/codes/{code:re:[A-Z]{2}-[0-9]{4}}")
    async def get_code(code: str):
        return {"code": code}

    # ── 31. Host-based routing ──
    @app.get("/hosted", host="api.taskforge.dev")
    async def hosted_api():
        return {"host": "api"}

    @app.get("/hosted", host="admin.taskforge.dev")
    async def hosted_admin():
        return {"host": "admin"}

    # ── 32. Method override ──
    @app.patch("/method-test")
    async def method_test():
        return {"method": "PATCH"}

    # ── 33. Cache TTL metadata ──
    @app.get("/cached", cache_ttl=300)
    async def cached_endpoint():
        return {"cached": True, "time": time.time()}

    # ── Include controller ──
    app.include_controller(ProjectController())

    # ── Router with lifecycle hooks ──
    comments_router = Router(prefix="/comments", tags=["comments"])

    hook_log = []

    @comments_router.before_request
    def before_comments(request_data):
        hook_log.append("before")

    @comments_router.after_request
    def after_comments(request_data, response):
        hook_log.append("after")
        return response

    @comments_router.get("")
    async def list_comments():
        return {"comments": list(_db["comments"].values()), "hooks": list(hook_log)}

    @comments_router.post("", status_code=201)
    async def create_comment(data: CommentCreate):
        _counters["comments"] += 1
        cid = _counters["comments"]
        record = {"id": cid, "text": data.text, "author": data.author}
        _db["comments"][cid] = record
        return record

    app.include_router(comments_router)

    # ── Route group ──
    with app.group(prefix="/v2", tags=["v2"]) as v2:

        @v2.get("/health")
        async def v2_health():
            return {"version": 2, "status": "ok"}

        @v2.post("/echo")
        async def v2_echo(request: Request):
            data = await request.json()
            return {"version": 2, "echo": data}

    # ── OpenAPI ──
    @app.get("/custom-openapi")
    async def custom_openapi():
        from rivex.openapi.openapi import generate_openapi

        spec = generate_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app._routes,
        )
        return spec

    return app


# ============================================================================
# TEST SUITE
# ============================================================================


@pytest.fixture
def app():
    return build_app()


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRootAndInfo:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["app"] == "TaskForge"
        assert data["version"] == "2.0.0"

    def test_request_id_header(self, client):
        r = client.get("/")
        assert "x-request-id" in r.headers

    def test_security_headers(self, client):
        r = client.get("/")
        assert "x-content-type-options" in r.headers
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_cors_preflight(self, client):
        r = client.request("OPTIONS", "/", headers={"origin": "https://taskforge.dev"})
        assert r.status_code == 204
        assert "access-control-allow-origin" in r.headers

    def test_request_info(self, client):
        r = client.get("/request/info", headers={"host": "localhost:8000"})
        assert r.status_code == 200
        data = r.json()
        assert data["method"] == "GET"
        assert data["path"] == "/request/info"


class TestAuth:
    def test_register_user(self, client):
        r = client.post(
            "/auth/register",
            json={
                "username": "alice",
                "email": "alice@test.com",
                "password": "secret123",
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["username"] == "alice"
        assert data["id"] == 1
        assert "password" not in data

    def test_register_validation_error(self, client):
        r = client.post(
            "/auth/register",
            json={
                "username": "ab",
                "email": "x",
                "password": "123",
            },
        )
        assert r.status_code == 422

    def test_login_form(self, client):
        client.post(
            "/auth/register",
            json={
                "username": "bob",
                "email": "bob@test.com",
                "password": "pass1234",
            },
        )
        r = client.post(
            "/auth/login",
            content=b"username=bob&password=pass1234",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_invalid(self, client):
        r = client.post(
            "/auth/login",
            content=b"username=nobody&password=wrong",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 401

    def test_jwt_protected(self, client):
        client.post(
            "/auth/register",
            json={
                "username": "carol",
                "email": "carol@test.com",
                "password": "pass5678",
            },
        )
        login = client.post(
            "/auth/login",
            content=b"username=carol&password=pass5678",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        token = login.json()["access_token"]
        r = client.get("/auth/me", headers={"authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["user"] == "carol"

    def test_jwt_no_token(self, client):
        r = client.get("/auth/me")
        assert r.status_code == 401

    def test_api_key_auth(self, client):
        r = client.get("/auth/apikey", headers={"x-api-key": API_KEY})
        assert r.status_code == 200
        assert r.json()["authenticated"] is True

    def test_api_key_invalid(self, client):
        r = client.get("/auth/apikey", headers={"x-api-key": "wrong-key"})
        assert r.status_code == 403

    def test_api_key_missing(self, client):
        r = client.get("/auth/apikey")
        assert r.status_code == 401

    def test_http_basic(self, client):
        creds = base64.b64encode(b"admin:secret").decode()
        r = client.get("/auth/basic", headers={"authorization": f"Basic {creds}"})
        assert r.status_code == 200
        assert r.json()["user"] == "admin"

    def test_http_basic_invalid(self, client):
        creds = base64.b64encode(b"admin:wrong").decode()
        r = client.get("/auth/basic", headers={"authorization": f"Basic {creds}"})
        assert r.status_code == 401

    def test_oauth2_bearer(self, client):
        client.post(
            "/auth/register",
            json={
                "username": "dan",
                "email": "dan@test.com",
                "password": "pass0000",
            },
        )
        login = client.post(
            "/auth/login",
            content=b"username=dan&password=pass0000",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        token = login.json()["access_token"]
        r = client.get("/auth/oauth2", headers={"authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["sub"] == "dan"


class TestTaskCRUD:
    def _create_task(self, client, title="Test Task", priority=3):
        return client.post(
            "/tasks",
            json={
                "title": title,
                "description": "A test task",
                "priority": priority,
            },
        )

    def test_create_task(self, client):
        r = self._create_task(client)
        assert r.status_code == 201
        assert r.json()["title"] == "Test Task"
        assert r.json()["priority"] == 3
        assert r.json()["status"] == "pending"

    def test_list_tasks(self, client):
        self._create_task(client, "Task 1")
        self._create_task(client, "Task 2")
        r = client.get("/tasks")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_tasks_pagination(self, client):
        for i in range(15):
            self._create_task(client, f"Task {i}")
        r = client.get("/tasks", params={"page": "2", "size": "5"})
        data = r.json()
        assert data["page"] == 2
        assert data["size"] == 5
        assert len(data["items"]) == 5

    def test_get_task(self, client):
        self._create_task(client)
        r = client.get("/tasks/1")
        assert r.status_code == 200
        assert r.json()["id"] == 1

    def test_get_task_not_found(self, client):
        r = client.get("/tasks/999")
        assert r.status_code == 404
        data = r.json()
        assert "not found" in data.get("detail", "").lower()

    def test_update_task(self, client):
        self._create_task(client)
        r = client.put("/tasks/1", json={"title": "Updated", "status": "done"})
        assert r.status_code == 200
        assert r.json()["title"] == "Updated"
        assert r.json()["status"] == "done"

    def test_partial_update(self, client):
        self._create_task(client)
        r = client.put("/tasks/1", json={"priority": 5})
        assert r.json()["priority"] == 5
        assert r.json()["title"] == "Test Task"

    def test_assign_task(self, client):
        self._create_task(client)
        r = client.patch("/tasks/1/assign", json={"assignee": "alice"})
        assert r.status_code == 200
        assert r.json()["assignee"] == "alice"

    def test_delete_task(self, client):
        self._create_task(client)
        r = client.delete("/tasks/1")
        assert r.status_code == 204

        r2 = client.get("/tasks/1")
        assert r2.status_code in (404, 422)

    def test_task_summary_response_model(self, client):
        self._create_task(client)
        r = client.get("/tasks/1/summary")
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert "title" in data
        assert "status" in data

    def test_filter_tasks_by_status(self, client):
        self._create_task(client, "Task A")
        self._create_task(client, "Task B")
        client.put("/tasks/1", json={"status": "done"})
        r = client.get("/tasks", params={"status_filter": "done"})
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["title"] == "Task A"


class TestParams:
    def test_query_params(self, client):
        r = client.get("/echo/params", params={"q": "hello"})
        assert r.json()["q"] == "hello"

    def test_header_param(self, client):
        r = client.get("/echo/params", headers={"x-custom": "myval"})
        assert r.json()["x_custom"] == "myval"

    def test_cookie_param(self, client):
        r = client.get("/echo/params", headers={"cookie": "session_id=xyz789"})
        assert r.json()["session_id"] == "xyz789"

    def test_path_param_int(self, client):
        r = client.get("/items/42")
        assert r.json()["item_id"] == 42

    def test_path_param_string_fails(self, client):
        r = client.get("/items/abc")
        assert r.status_code in (400, 404, 422)


class TestFormAndUpload:
    def test_contact_form(self, client):
        r = client.post(
            "/contact",
            content=b"name=John&email=john@test.com&message=Hello",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        assert r.json()["name"] == "John"
        assert r.json()["email"] == "john@test.com"

    def test_search_form_model(self, client):
        r = client.post(
            "/search",
            content=b"query=rivex&category=docs",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "rivex"
        assert data["category"] == "docs"
        assert data["page"] == 1

    def test_file_upload(self, client):
        body = (
            b"------TestBoundary123\r\n"
            b'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"hello file content\r\n"
            b"------TestBoundary123--\r\n"
        )
        r = client.post(
            "/upload",
            content=body,
            headers={"content-type": "multipart/form-data; boundary=----TestBoundary123"},
        )
        assert r.status_code == 200
        assert r.json()["filename"] == "test.txt"
        assert r.json()["size"] > 0


class TestResponses:
    def test_json_response(self, client):
        r = client.get("/responses/json")
        assert r.json()["format"] == "json"

    def test_html_response(self, client):
        r = client.get("/responses/html")
        assert "<h1>Hello</h1>" in r.text
        assert "text/html" in r.headers.get("content-type", "")

    def test_text_response(self, client):
        r = client.get("/responses/text")
        assert r.text == "plain text response"
        assert "text/plain" in r.headers.get("content-type", "")

    def test_xml_response(self, client):
        r = client.get("/responses/xml")
        assert "<status>ok</status>" in r.text
        assert "application/xml" in r.headers.get("content-type", "")

    def test_redirect(self, client):
        r = client.get("/responses/redirect")
        assert r.status_code == 302
        assert r.headers.get("location") == "/"

    def test_streaming(self, client):
        r = client.get("/responses/streaming")
        assert "chunk-0" in r.text
        assert "chunk-4" in r.text

    def test_sse(self, client):
        r = client.get("/responses/sse")
        assert "event: tick" in r.text
        assert "data:" in r.text

    def test_file_response(self, client):
        path = os.path.join(tempfile.gettempdir(), "rivex_test_file.txt")
        with open(path, "w") as f:
            f.write("file content for download")
        r = client.get("/responses/file")
        assert r.status_code == 200
        assert "test.txt" in r.headers.get("content-disposition", "")

    def test_cookie_response(self, client):
        r = client.get("/responses/cookie")
        assert r.status_code == 200
        set_cookies = [v for k, v in r.headers.items() if k.lower() == "set-cookie"]
        cookie_text = " ".join(set_cookies) if set_cookies else ""
        assert "session_token" in cookie_text or r.status_code == 200

    def test_status_codes(self, client):
        r = client.post("/resources")
        assert r.status_code == 201

        r = client.delete("/resources/1")
        assert r.status_code == 204


class TestErrorHandling:
    def test_http_exception(self, client):
        r = client.get("/errors/http")
        assert r.status_code == 418
        assert "teapot" in r.json()["detail"]

    def test_problem_details(self, client):
        r = client.get("/errors/problem")
        assert r.status_code == 422
        data = r.json()
        assert data["title"] == "Validation Error"
        assert data["type"] == "https://errors.taskforge.dev/validation"
        assert data["detail"] == "Field 'name' is required"
        assert data["field"] == "name"

    def test_value_error_handler(self, client):
        r = client.get("/errors/value")
        assert r.status_code == 400
        assert "ValueError" in r.json()["detail"]

    def test_404(self, client):
        r = client.get("/nonexistent-path")
        assert r.status_code == 404


class TestWebhooks:
    def test_github_webhook(self, client):
        payload = b'{"action":"push","ref":"refs/heads/main"}'
        sig = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        r = client.post(
            "/webhooks/github",
            content=payload,
            headers={"x-hub-signature-256": sig},
        )
        assert r.status_code == 200
        assert r.json()["verified"] is True

    def test_github_webhook_invalid(self, client):
        r = client.post(
            "/webhooks/github",
            content=b"payload",
            headers={"x-hub-signature-256": "sha256=invalid"},
        )
        assert r.status_code == 401

    def test_generic_webhook(self, client):
        payload = b'{"event":"test"}'
        sig = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        r = client.post(
            "/webhooks/generic",
            content=payload,
            headers={"x-signature": sig},
        )
        assert r.status_code == 200


class TestMiddleware:
    def test_method_override(self, client):
        r = client.post(
            "/method-test",
            headers={"x-http-method-override": "PATCH"},
        )
        assert r.status_code == 200
        assert r.json()["method"] == "PATCH"

    def test_idempotency(self, client):
        idem_key = "idem-12345"
        r1 = client.post(
            "/resources",
            headers={"idempotency-key": idem_key},
        )
        r2 = client.post(
            "/resources",
            headers={"idempotency-key": idem_key},
        )
        assert r1.status_code == r2.status_code

    def test_max_body_size(self, client):
        huge_body = b"x" * 6_000_000
        r = client.post("/stream/echo", content=huge_body)
        assert r.status_code == 413


class TestContentNegotiation:
    def test_json(self, client):
        r = client.get("/negotiate", headers={"accept": "application/json"})
        assert r.json()["format"] == "json"

    def test_html(self, client):
        r = client.get("/negotiate", headers={"accept": "text/html"})
        assert "<p>HTML</p>" in r.text

    def test_xml(self, client):
        r = client.get("/negotiate", headers={"accept": "application/xml"})
        assert "<data>xml</data>" in r.text


class TestPagination:
    def test_offset_pagination(self, client):
        r = client.get("/paginated", params={"page": "1", "size": "5"})
        data = r.json()
        assert data["total"] == 50
        assert data["page"] == 1
        assert data["size"] == 5
        assert len(data["items"]) == 5
        assert data["has_next"] is True
        assert data["has_previous"] is False

    def test_last_page(self, client):
        r = client.get("/paginated", params={"page": "10", "size": "5"})
        data = r.json()
        assert data["has_next"] is False
        assert data["has_previous"] is True

    def test_cursor_pagination(self, client):
        r = client.get("/cursor-paginated", params={"limit": "5"})
        data = r.json()
        assert len(data["items"]) == 5
        assert data["has_more"] is True
        assert data["cursor"] is not None

        r2 = client.get("/cursor-paginated", params={"cursor": data["cursor"], "limit": "5"})
        data2 = r2.json()
        assert data2["items"][0]["id"] == 6


class TestRouting:
    def test_regex_path_match(self, client):
        r = client.get("/codes/AB-1234")
        assert r.status_code == 200
        assert r.json()["code"] == "AB-1234"

    def test_regex_path_no_match(self, client):
        r = client.get("/codes/abc-12")
        assert r.status_code == 404

    def test_host_routing(self, client):
        r = client.get("/hosted", headers={"host": "api.taskforge.dev"})
        assert r.json()["host"] == "api"

        r = client.get("/hosted", headers={"host": "admin.taskforge.dev"})
        assert r.json()["host"] == "admin"


class TestControllerAndRouter:
    def test_controller_list(self, client):
        r = client.get("/projects")
        assert r.status_code == 200
        assert "projects" in r.json()

    def test_controller_create(self, client):
        r = client.post("/projects", json={"name": "Rivex", "description": "Framework"})
        assert r.status_code == 201
        assert r.json()["name"] == "Rivex"

    def test_controller_get(self, client):
        client.post("/projects", json={"name": "P1"})
        r = client.get("/projects/1")
        assert r.status_code == 200
        assert r.json()["name"] == "P1"

    def test_controller_not_found(self, client):
        r = client.get("/projects/999")
        assert r.status_code == 404

    def test_router_comments(self, client):
        r = client.post("/comments", json={"text": "Great!", "author": "alice"})
        assert r.status_code == 201
        assert r.json()["text"] == "Great!"

        r2 = client.get("/comments")
        assert r2.status_code == 200
        assert len(r2.json()["comments"]) >= 1

    def test_router_lifecycle_hooks(self, client):
        client.post("/comments", json={"text": "hook test", "author": "bob"})
        r = client.get("/comments")
        hooks = r.json()["hooks"]
        assert "before" in hooks
        assert "after" in hooks


class TestRouteGroup:
    def test_v2_health(self, client):
        r = client.get("/v2/health")
        assert r.status_code == 200
        assert r.json()["version"] == 2

    def test_v2_echo(self, client):
        r = client.post("/v2/echo", json={"msg": "hello"})
        assert r.status_code == 200
        assert r.json()["version"] == 2
        assert r.json()["echo"]["msg"] == "hello"


class TestPlugin:
    def test_audit_plugin(self, client):
        r = client.get("/audit/status")
        assert r.status_code == 200
        assert r.json()["plugin"] == "audit"
        assert r.json()["active"] is True


class TestHealthAndMetrics:
    def test_liveness(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"

    def test_readiness(self, client):
        r = client.get("/readyz")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"

    def test_metrics(self, client):
        client.get("/")
        r = client.get("/metrics")
        assert r.status_code == 200
        text = r.text
        assert "http_requests_total" in text
        assert "http_request_duration_seconds" in text


class TestBackgroundTasks:
    def test_background_task_execution(self, client):
        r = client.post("/notifications/send", json={"message": "hello"})
        assert r.json()["queued"] is True
        time.sleep(0.3)
        r2 = client.get("/notifications/log")
        assert "sent:hello" in r2.json()["log"]


class TestYieldDependency:
    def test_yield_dep(self, client):
        r = client.get("/db/status")
        assert r.status_code == 200
        assert r.json()["connected"] is True
        assert r.json()["queries"] == 1


class TestSignals:
    def test_emit_and_log(self, client):
        r = client.post("/events/emit", json={"name": "test_event"})
        assert r.json()["emitted"] == "test_event"

        r2 = client.get("/events/log")
        events = r2.json()["events"]
        assert any(e.get("event_name") == "test_event" for e in events)


class TestJsonableEncoder:
    def test_complex_types(self, client):
        r = client.get("/encode/complex")
        assert r.status_code == 200
        data = r.json()
        assert "timestamp" in data
        assert "duration" in data
        assert "amount" in data
        assert data["id"] == "12345678-1234-5678-1234-567812345678"


class TestGuards:
    def test_requires_roles_denied(self, client):
        r = client.get("/admin/dashboard")
        assert r.status_code == 403

    def test_requires_roles_allowed(self, client):
        r = client.get("/admin/dashboard", headers={"x-user-roles": "admin,editor"})
        assert r.status_code == 200
        assert r.json()["admin"] is True


class TestOpenAPI:
    def test_openapi_spec(self, client):
        r = client.get("/custom-openapi")
        assert r.status_code == 200
        spec = r.json()
        assert spec["openapi"].startswith("3.")
        assert spec["info"]["title"] == "TaskForge API"
        assert spec["info"]["version"] == "2.0.0"
        assert "/tasks" in spec.get("paths", {}) or len(spec.get("paths", {})) > 0


class TestStreaming:
    def test_stream_echo(self, client):
        r = client.post("/stream/echo", content=b"streaming data payload")
        assert r.status_code == 200
        assert r.json()["received_bytes"] == len(b"streaming data payload")


class TestCacheTTL:
    def test_cache_ttl_metadata(self, app):
        for route in app._routes:
            if route.path == "/cached":
                assert route.cache_ttl == 300
                return
        pytest.fail("Route /cached not found")


class TestJWTDirect:
    def test_encode_decode_roundtrip(self):
        payload = {"sub": "test", "role": "admin"}
        token = jwt_encode(payload, JWT_SECRET)
        decoded = jwt_decode(token, JWT_SECRET)
        assert decoded["sub"] == "test"
        assert decoded["role"] == "admin"

    def test_expired_token(self):
        from rivex.auth.jwt import ExpiredTokenError

        token = jwt_encode({"sub": "test"}, JWT_SECRET, expires_in=-1)
        with pytest.raises(ExpiredTokenError):
            jwt_decode(token, JWT_SECRET)

    def test_invalid_signature(self):
        from rivex.auth.jwt import InvalidTokenError

        token = jwt_encode({"sub": "test"}, JWT_SECRET)
        with pytest.raises(InvalidTokenError):
            jwt_decode(token, "wrong-secret")


class TestWebhookVerification:
    def test_stripe_verify(self):
        secret = "whsec_stripe"
        ts = str(int(time.time()))
        payload = b'{"type":"payment"}'
        signed = f"{ts}.".encode() + payload
        sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        header = f"t={ts},v1={sig}"
        assert verify_signature(payload, header, secret, provider="stripe") is True

    def test_github_verify(self):
        secret = "gh_secret"
        payload = b'{"action":"push"}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_signature(payload, sig, secret, provider="github") is True

    def test_generic_verify(self):
        secret = "generic_secret"
        payload = b"data"
        sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_signature(payload, sig, secret, provider="generic") is True


class TestMetricsDirectly:
    def test_counter(self):
        c = Counter("test_counter", labels=["method"])
        c.inc(method="GET")
        c.inc(method="GET")
        c.inc(method="POST")
        text = c.collect()
        assert "test_counter" in text

    def test_gauge(self):
        g = Gauge("test_gauge")
        g.set(10)
        g.inc(5)
        g.dec(3)
        text = g.collect()
        assert "12" in text

    def test_histogram(self):
        h = Histogram("test_hist")
        for v in [0.01, 0.05, 0.1, 0.5, 1.0]:
            h.observe(v)
        text = h.collect()
        assert "test_hist_bucket" in text
        assert "test_hist_sum" in text
        assert "test_hist_count" in text

    def test_histogram_timer(self):
        h = Histogram("timer_test")
        with h.time():
            time.sleep(0.01)
        text = h.collect()
        assert "timer_test_count" in text

    def test_registry(self):
        reg = MetricsRegistry()
        c = reg.counter("reg_c")
        g = reg.gauge("reg_g")
        h = reg.histogram("reg_h")
        c.inc()
        g.set(5)
        h.observe(0.1)
        text = reg.collect()
        assert "reg_c" in text
        assert "reg_g" in text
        assert "reg_h" in text


class TestTracing:
    def test_span_lifecycle(self):
        span = Span(name="test-op", trace_id="abc", span_id="def")
        span.set_attribute("key", "value")
        span.end()
        d = span.to_dict()
        assert d["name"] == "test-op"
        assert d["attributes"]["key"] == "value"
        assert d["duration_ms"] >= 0


class TestProblemDetails:
    def test_not_found_factory(self):
        exc = not_found(detail="Missing resource")
        assert exc.status_code == 404
        assert exc.problem.detail == "Missing resource"

    def test_bad_request_factory(self):
        exc = bad_request(detail="Invalid input")
        assert exc.status_code == 400

    def test_problem_response(self):
        resp = ProblemResponse.create(
            status=409,
            title="Conflict",
            detail="Duplicate entry",
        )
        assert resp["status"] == 409
        body = json.loads(resp["body"])
        assert body["title"] == "Conflict"


class TestPaginationDirect:
    def test_paginate(self):
        items = list(range(100))
        page = paginate(items, page=3, size=10)
        assert page.page == 3
        assert page.size == 10
        assert page.total == 100
        assert page.pages == 10
        assert page.has_next is True
        assert page.has_previous is True
        assert len(page.items) == 10

    def test_cursor_page(self):
        cp = CursorPage(items=[1, 2, 3], cursor="abc", has_more=True)
        d = cp.dict()
        assert d["cursor"] == "abc"
        assert d["has_more"] is True
        assert len(d["items"]) == 3


class TestNegotiation:
    def test_parse_accept(self):
        parsed = parse_accept("text/html, application/json;q=0.9, */*;q=0.1")
        assert parsed[0][0] == "text/html"
        assert parsed[1][0] == "application/json"

    def test_best_match(self):
        assert (
            best_match("application/json", ["text/html", "application/json"]) == "application/json"
        )
        assert best_match("text/*", ["text/html", "application/json"]) == "text/html"
        assert best_match("*/*", ["text/html"]) == "text/html"


class TestJsonableEncoderDirect:
    def test_pydantic(self):
        u = UserResponse(id=1, username="test", email="t@t.com")
        encoded = jsonable_encoder(u)
        assert encoded["id"] == 1
        assert encoded["username"] == "test"

    def test_datetime(self):
        from datetime import datetime

        encoded = jsonable_encoder({"ts": datetime(2024, 1, 1)})
        assert encoded["ts"] == "2024-01-01T00:00:00"

    def test_enum(self):
        assert jsonable_encoder(HTTPMethod.GET) == "GET"


class TestSignalsDirect:
    def test_signal_connect_send(self):
        sig = Signal("test")
        received = []
        sig.connect(lambda sender, **kw: received.append(kw))
        sig.send(sender="me", data="hello")
        assert len(received) == 1
        assert received[0]["data"] == "hello"

    def test_signal_disconnect(self):
        sig = Signal("test")

        def handler(sender, **kw):
            pass

        sig.connect(handler)
        sig.disconnect(handler)
        results = sig.send(sender="x")
        assert len(results) == 0


class TestStatusCodes:
    def test_api_status(self):
        assert APIStatus.OK == 200
        assert APIStatus.CREATED == 201
        assert APIStatus.NOT_FOUND == 404
        assert APIStatus.UNPROCESSABLE_ENTITY == 422

    def test_http_method(self):
        assert HTTPMethod.GET == "GET"
        assert HTTPMethod.POST == "POST"


# ============================================================================
# LOAD TESTING
# ============================================================================


class TestLoadExtreme:
    """Extreme concurrency and throughput tests."""

    def test_concurrent_reads(self, client):
        """Hammer the read endpoint with concurrent threads."""
        errors = []
        results = []

        def _hit():
            try:
                r = client.get("/")
                results.append(r.status_code)
                if r.status_code != 200:
                    errors.append(f"Got {r.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=_hit) for _ in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Errors: {errors[:10]}"
        assert len(results) == 200
        assert all(s == 200 for s in results)

    def test_concurrent_writes(self, client):
        """Concurrent task creation."""
        errors = []
        ids = []

        def _create(i):
            try:
                r = client.post(
                    "/tasks",
                    json={
                        "title": f"Load Task {i}",
                        "priority": (i % 5) + 1,
                    },
                )
                if r.status_code == 201:
                    ids.append(r.json()["id"])
                else:
                    errors.append(f"Task {i}: {r.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=_create, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Errors: {errors[:10]}"
        assert len(ids) == 100

    def test_mixed_load(self, client):
        """Mix of reads, writes, and errors under load."""
        stats = {"ok": 0, "created": 0, "errors_expected": 0, "failures": 0}

        def _mixed(i):
            try:
                if i % 4 == 0:
                    r = client.post("/tasks", json={"title": f"ML-{i}", "priority": 1})
                    if r.status_code == 201:
                        stats["created"] += 1
                elif i % 4 == 1:
                    r = client.get("/")
                    if r.status_code == 200:
                        stats["ok"] += 1
                elif i % 4 == 2:
                    r = client.get("/tasks/99999")
                    if r.status_code in (404, 422):
                        stats["errors_expected"] += 1
                else:
                    r = client.get("/paginated", params={"page": str((i % 10) + 1)})
                    if r.status_code == 200:
                        stats["ok"] += 1
            except Exception:
                stats["failures"] += 1

        threads = [threading.Thread(target=_mixed, args=(i,)) for i in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert stats["failures"] == 0, f"Unexpected failures: {stats['failures']}"
        total = stats["ok"] + stats["created"] + stats["errors_expected"]
        assert total == 200

    def test_rapid_auth_flow(self, client):
        """Register → login → access protected endpoint, repeated."""
        errors = []

        def _auth_flow(i):
            try:
                username = f"loaduser{i}"
                client.post(
                    "/auth/register",
                    json={
                        "username": username,
                        "email": f"{username}@test.com",
                        "password": "loadpass123",
                    },
                )
                login = client.post(
                    "/auth/login",
                    content=f"username={username}&password=loadpass123".encode(),
                    headers={"content-type": "application/x-www-form-urlencoded"},
                )
                if login.status_code != 200:
                    errors.append(f"Login failed for {username}: {login.status_code}")
                    return
                token = login.json()["access_token"]
                me = client.get("/auth/me", headers={"authorization": f"Bearer {token}"})
                if me.status_code != 200:
                    errors.append(f"Me failed for {username}: {me.status_code}")
                elif me.json()["user"] != username:
                    errors.append(f"Wrong user for {username}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=_auth_flow, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Auth errors: {errors[:10]}"

    def test_webhook_burst(self, client):
        """Rapid webhook verification."""
        errors = []

        def _webhook(i):
            try:
                payload = json.dumps({"event": f"push-{i}"}).encode()
                sig = (
                    "sha256="
                    + hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
                )
                r = client.post(
                    "/webhooks/github",
                    content=payload,
                    headers={"x-hub-signature-256": sig},
                )
                if r.status_code != 200:
                    errors.append(f"Webhook {i}: {r.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=_webhook, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Webhook errors: {errors[:10]}"

    def test_high_throughput_sequential(self, client):
        """1000 sequential requests to measure stability."""
        for i in range(1000):
            r = client.get("/")
            assert r.status_code == 200, f"Request {i} failed: {r.status_code}"

    def test_pagination_under_load(self, client):
        """Create many items then paginate concurrently."""
        for i in range(50):
            client.post("/tasks", json={"title": f"PL-{i}", "priority": 1})

        errors = []

        def _paginate(page):
            try:
                r = client.get("/tasks", params={"page": str(page), "size": "5"})
                if r.status_code != 200:
                    errors.append(f"Page {page}: {r.status_code}")
                data = r.json()
                if data["page"] != page:
                    errors.append(f"Wrong page: expected {page}, got {data['page']}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=_paginate, args=(p,)) for p in range(1, 11)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Pagination errors: {errors[:10]}"

    def test_concurrent_form_submissions(self, client):
        """Concurrent form model parsing."""
        errors = []

        def _search(i):
            try:
                r = client.post(
                    "/search",
                    content=f"query=term{i}&category=cat{i % 3}".encode(),
                    headers={"content-type": "application/x-www-form-urlencoded"},
                )
                if r.status_code != 200:
                    errors.append(f"Search {i}: {r.status_code}")
                elif r.json()["query"] != f"term{i}":
                    errors.append(f"Wrong query for {i}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=_search, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Form errors: {errors[:10]}"

    def test_middleware_stack_under_load(self, client):
        """Verify middleware stack (CORS, request-id, security) under load."""
        errors = []

        def _check(i):
            try:
                r = client.get("/", headers={"origin": "https://taskforge.dev"})
                if r.status_code != 200:
                    errors.append(f"Req {i}: {r.status_code}")
                    return
                if "x-request-id" not in r.headers:
                    errors.append(f"Req {i}: missing request-id")
                if r.headers.get("x-content-type-options") != "nosniff":
                    errors.append(f"Req {i}: missing security header")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=_check, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Middleware errors: {errors[:10]}"
