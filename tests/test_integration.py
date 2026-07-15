"""Integration tests for Rivex Python SDK.

These tests exercise the full Python stack -- app creation, route registration,
handler wrapping with injection, middleware logic, request/response classes,
and OpenAPI generation -- without requiring the Rust runtime.
"""

import json

import pytest
from pydantic import BaseModel

from rivex import (
    BackgroundTask,
    BackgroundTasks,
    CORSMiddleware,
    Depends,
    GZipMiddleware,
    Headers,
    HTMLResponse,
    HTTPException,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    Rivex,
    Router,
    status,
)
from rivex.core._injection import _coerce, _normalize_response, build_handler_wrapper
from rivex.openapi.openapi import generate_openapi


def _json_body(result):
    if "body_json" in result:
        return result["body_json"]
    return json.loads(result["body"])


# -- Models --


class UserCreate(BaseModel):
    name: str
    email: str
    age: int = 25


class UserResponse(BaseModel):
    id: int
    name: str
    email: str


# -- App Factory --


def create_test_app():
    """Create a fully configured Rivex app for testing."""
    app = Rivex(title="Test API", version="0.1.0", description="Integration test API")

    # Router with prefix
    api = Router(prefix="/api/v1", tags=["api"])

    @api.get("/users", tags=["users"])
    async def list_users():
        return [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    @api.post("/users", status_code=201, tags=["users"])
    async def create_user(user: UserCreate):
        return UserResponse(id=1, name=user.name, email=user.email)

    @api.get("/users/{user_id}")
    async def get_user(user_id: int):
        if user_id == 999:
            raise HTTPException(404, detail="User not found")
        return {"id": user_id, "name": "Alice"}

    @api.delete("/users/{user_id}", status_code=204)
    async def delete_user(user_id: int):
        pass

    app.include_router(api)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/search")
    async def search(q: str, limit: int = 10, offset: int = 0):
        return {"q": q, "limit": limit, "offset": offset}

    return app


# -- Test: App Configuration --


class TestAppConfiguration:
    def test_app_metadata(self):
        app = create_test_app()
        assert app.title == "Test API"
        assert app.version == "0.1.0"
        assert app.description == "Integration test API"

    def test_route_count(self):
        app = create_test_app()
        paths = [r.path for r in app._routes]
        assert "/health" in paths
        assert "/search" in paths
        assert "/api/v1/users" in paths
        assert "/api/v1/users/{user_id}" in paths

    def test_route_methods(self):
        app = create_test_app()
        route_map = {(r.method, r.path) for r in app._routes}
        assert ("GET", "/api/v1/users") in route_map
        assert ("POST", "/api/v1/users") in route_map
        assert ("GET", "/api/v1/users/{user_id}") in route_map
        assert ("DELETE", "/api/v1/users/{user_id}") in route_map

    def test_route_tags_merged(self):
        app = create_test_app()
        for r in app._routes:
            if r.path == "/api/v1/users" and r.method == "GET":
                assert "api" in r.tags
                assert "users" in r.tags

    def test_route_status_codes(self):
        app = create_test_app()
        for r in app._routes:
            if r.path == "/api/v1/users" and r.method == "POST":
                assert r.status_code == 201
            if r.path == "/api/v1/users/{user_id}" and r.method == "DELETE":
                assert r.status_code == 204


# -- Test: Handler Wrapping & Injection --


class TestHandlerInjection:
    def test_coerce_int(self):
        assert _coerce("42", int) == 42

    def test_coerce_float(self):
        assert _coerce("3.14", float) == 3.14

    def test_coerce_bool_true(self):
        assert _coerce("true", bool) is True
        assert _coerce("1", bool) is True
        assert _coerce("yes", bool) is True

    def test_coerce_bool_false(self):
        assert _coerce("false", bool) is False
        assert _coerce("0", bool) is False

    def test_coerce_string(self):
        assert _coerce("hello", str) == "hello"

    def test_normalize_dict(self):
        result = _normalize_response({"key": "value"}, 200)
        assert result["status"] == 200
        assert b"key" in result["body"]

    def test_normalize_none_204(self):
        result = _normalize_response(None, 204)
        assert result["status"] == 204

    def test_normalize_none_always_204(self):
        # _normalize_response returns 204 for None regardless of default_status
        result = _normalize_response(None, 200)
        assert result["status"] == 204

    def test_normalize_string(self):
        result = _normalize_response("hello", 200)
        assert result["body"] == b"hello"
        # Check content-type is text
        headers = dict(result.get("headers", []))
        assert "text/plain" in headers.get("content-type", "")

    def test_normalize_pydantic_model(self):
        user = UserResponse(id=1, name="Alice", email="alice@example.com")
        result = _normalize_response(user, 200)
        assert result["status"] == 200
        assert b"Alice" in result["body"]

    def test_normalize_tuple_with_status(self):
        # Tuple format is (status_code, body)
        result = _normalize_response((201, {"msg": "created"}), 200)
        assert result["status"] == 201

    def test_normalize_response_object(self):
        resp = JSONResponse({"test": True}, status_code=201)
        result = _normalize_response(resp, 200)
        assert result["status"] == 201

    def test_normalize_bytes(self):
        result = _normalize_response(b"raw bytes", 200)
        assert result["status"] == 200
        assert result["body"] == b"raw bytes"
        headers = dict(result.get("headers", []))
        assert headers.get("content-type") == "application/octet-stream"

    def test_normalize_list(self):
        result = _normalize_response([1, 2, 3], 200)
        assert result["status"] == 200
        assert json.loads(result["body"]) == [1, 2, 3]


# -- Test: Response Classes --


class TestResponses:
    def test_json_response(self):
        resp = JSONResponse({"key": "value"})
        rendered = resp._to_raw()
        assert rendered["status"] == 200
        assert b"key" in rendered["body"]
        headers = dict(rendered["headers"])
        assert headers["content-type"] == "application/json"

    def test_json_response_custom_status(self):
        resp = JSONResponse({"error": "not found"}, status_code=404)
        rendered = resp._to_raw()
        assert rendered["status"] == 404

    def test_html_response(self):
        resp = HTMLResponse("<h1>Hello</h1>")
        rendered = resp._to_raw()
        assert rendered["body"] == b"<h1>Hello</h1>"
        headers = dict(rendered["headers"])
        assert "text/html" in headers["content-type"]

    def test_plaintext_response(self):
        resp = PlainTextResponse("hello world")
        rendered = resp._to_raw()
        assert rendered["body"] == b"hello world"
        headers = dict(rendered["headers"])
        assert "text/plain" in headers["content-type"]

    def test_redirect_response(self):
        resp = RedirectResponse("/new-url")
        rendered = resp._to_raw()
        assert rendered["status"] == 307
        headers = dict(rendered["headers"])
        assert headers["location"] == "/new-url"

    def test_redirect_custom_status(self):
        resp = RedirectResponse("/new-url", status_code=301)
        rendered = resp._to_raw()
        assert rendered["status"] == 301

    def test_response_custom_headers(self):
        resp = JSONResponse(
            {"ok": True},
            headers={"x-custom": "value"},
        )
        rendered = resp._to_raw()
        headers = dict(rendered["headers"])
        assert headers["x-custom"] == "value"
        assert headers["content-type"] == "application/json"

    def test_response_none_content(self):
        resp = Response(content=None, status_code=204)
        rendered = resp._to_raw()
        assert rendered["status"] == 204
        assert rendered["body"] == b""


# -- Test: Headers --


class TestHeaders:
    def test_headers_get(self):
        h = Headers([("content-type", "application/json"), ("x-custom", "value")])
        assert h.get("content-type") == "application/json"
        assert h.get("x-custom") == "value"

    def test_headers_case_insensitive(self):
        h = Headers([("Content-Type", "application/json")])
        assert h.get("content-type") == "application/json"
        assert h.get("CONTENT-TYPE") == "application/json"

    def test_headers_missing(self):
        h = Headers([])
        assert h.get("missing") is None

    def test_headers_getlist(self):
        h = Headers([("x-val", "a"), ("x-val", "b")])
        assert h.getlist("x-val") == ["a", "b"]

    def test_headers_iter_yields_keys(self):
        h = Headers([("a", "1"), ("b", "2")])
        keys = list(h)
        assert "a" in keys
        assert "b" in keys

    def test_headers_len(self):
        h = Headers([("a", "1"), ("b", "2"), ("c", "3")])
        assert len(h) == 3

    def test_headers_contains(self):
        h = Headers([("Authorization", "Bearer token")])
        assert "authorization" in h
        assert "Authorization" in h
        assert "missing" not in h

    def test_headers_getitem(self):
        h = Headers([("x-key", "val")])
        assert h["x-key"] == "val"

    def test_headers_getitem_missing_raises(self):
        h = Headers([])
        with pytest.raises(KeyError):
            h["missing"]


# -- Test: Dependencies --


class TestDependencies:
    def test_depends_repr(self):
        def get_db():
            return "db_conn"

        d = Depends(get_db)
        assert "get_db" in repr(d)

    def test_depends_cache_default(self):
        d = Depends(lambda: "val")
        assert d.use_cache is True

    def test_depends_no_cache(self):
        d = Depends(lambda: "val", use_cache=False)
        assert d.use_cache is False


# -- Test: Exception Handling --


class TestExceptionHandling:
    def test_http_exception_attributes(self):
        exc = HTTPException(404, detail="Not found")
        assert exc.status_code == 404
        assert exc.detail == "Not found"

    def test_http_exception_default_detail(self):
        exc = HTTPException(500)
        assert exc.status_code == 500
        assert exc.detail == "Internal Server Error"

    def test_http_exception_with_headers(self):
        exc = HTTPException(401, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"})
        assert exc.headers == {"WWW-Authenticate": "Bearer"}

    def test_exception_handler_registration(self):
        app = Rivex()

        @app.exception_handler(ValueError)
        async def handle_value_error(request, exc):
            return JSONResponse({"error": str(exc)}, status_code=400)

        assert ValueError in app._exception_handlers


# -- Test: OpenAPI Generation --


class TestOpenAPIGeneration:
    def test_full_spec(self):
        app = create_test_app()
        spec = generate_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app._routes,
        )
        assert spec["openapi"] == "3.1.0"
        assert spec["info"]["title"] == "Test API"
        assert spec["info"]["version"] == "0.1.0"
        assert spec["info"]["description"] == "Integration test API"

    def test_paths_present(self):
        app = create_test_app()
        spec = generate_openapi(
            title=app.title,
            version=app.version,
            routes=app._routes,
        )
        assert "/api/v1/users" in spec["paths"]
        assert "/api/v1/users/{user_id}" in spec["paths"]
        assert "/health" in spec["paths"]
        assert "/search" in spec["paths"]

    def test_post_has_request_body(self):
        app = create_test_app()
        spec = generate_openapi(
            title=app.title,
            version=app.version,
            routes=app._routes,
        )
        post_op = spec["paths"]["/api/v1/users"]["post"]
        assert "requestBody" in post_op

    def test_query_params_in_search(self):
        app = create_test_app()
        spec = generate_openapi(
            title=app.title,
            version=app.version,
            routes=app._routes,
        )
        get_op = spec["paths"]["/search"]["get"]
        param_names = [p["name"] for p in get_op["parameters"]]
        assert "q" in param_names
        assert "limit" in param_names
        assert "offset" in param_names

    def test_tags_collected(self):
        app = create_test_app()
        spec = generate_openapi(
            title=app.title,
            version=app.version,
            routes=app._routes,
        )
        tag_names = [t["name"] for t in spec.get("tags", [])]
        assert "api" in tag_names
        assert "users" in tag_names

    def test_schema_components(self):
        app = create_test_app()
        spec = generate_openapi(
            title=app.title,
            version=app.version,
            routes=app._routes,
        )
        assert "components" in spec
        assert "schemas" in spec["components"]
        assert "UserCreate" in spec["components"]["schemas"]

    def test_path_params_in_spec(self):
        app = create_test_app()
        spec = generate_openapi(
            title=app.title,
            version=app.version,
            routes=app._routes,
        )
        get_op = spec["paths"]["/api/v1/users/{user_id}"]["get"]
        param_names = [p["name"] for p in get_op.get("parameters", [])]
        assert "user_id" in param_names
        # Path params must be required
        for p in get_op["parameters"]:
            if p["name"] == "user_id":
                assert p["required"] is True
                assert p["in"] == "path"


# -- Test: Middleware Registration --


class TestMiddleware:
    def test_cors_middleware_registration(self):
        app = Rivex()
        app.add_middleware(CORSMiddleware, allow_origins=["*"])
        assert len(app._middleware) == 1

    def test_gzip_middleware_registration(self):
        app = Rivex()
        app.add_middleware(GZipMiddleware)
        assert len(app._middleware) == 1

    def test_multiple_middleware(self):
        app = Rivex()
        app.add_middleware(CORSMiddleware, allow_origins=["*"])
        app.add_middleware(GZipMiddleware)
        assert len(app._middleware) == 2

    def test_middleware_stores_cls_and_kwargs(self):
        app = Rivex()
        app.add_middleware(CORSMiddleware, allow_origins=["http://localhost"])
        cls, kwargs = app._middleware[0]
        assert cls is CORSMiddleware
        assert kwargs["allow_origins"] == ["http://localhost"]


# -- Test: Status Codes --


class TestStatusCodes:
    def test_common_codes(self):
        assert status.HTTP_200_OK == 200
        assert status.HTTP_201_CREATED == 201
        assert status.HTTP_204_NO_CONTENT == 204
        assert status.HTTP_400_BAD_REQUEST == 400
        assert status.HTTP_401_UNAUTHORIZED == 401
        assert status.HTTP_403_FORBIDDEN == 403
        assert status.HTTP_404_NOT_FOUND == 404
        assert status.HTTP_405_METHOD_NOT_ALLOWED == 405
        assert status.HTTP_422_UNPROCESSABLE_ENTITY == 422
        assert status.HTTP_500_INTERNAL_SERVER_ERROR == 500

    def test_redirect_codes(self):
        assert status.HTTP_301_MOVED_PERMANENTLY == 301
        assert status.HTTP_302_FOUND == 302
        assert status.HTTP_307_TEMPORARY_REDIRECT == 307
        assert status.HTTP_308_PERMANENT_REDIRECT == 308


# -- Test: Background Tasks --


class TestBackgroundTasks:
    def test_background_task_creation(self):
        def my_task(x):
            pass

        bt = BackgroundTask(my_task, 42)
        assert bt is not None
        assert bt.func is my_task
        assert bt.args == (42,)

    def test_background_tasks_add(self):
        tasks = BackgroundTasks()
        tasks.add_task(lambda: None)
        assert len(tasks._tasks) == 1

    def test_background_tasks_multiple(self):
        tasks = BackgroundTasks()
        tasks.add_task(lambda: None)
        tasks.add_task(lambda: None)
        tasks.add_task(lambda: None)
        assert len(tasks._tasks) == 3

    def test_background_task_callable(self):
        results = []

        def my_task(val):
            results.append(val)

        bt = BackgroundTask(my_task, "hello")
        bt()
        assert results == ["hello"]


# -- Test: Lifecycle Hooks --


class TestLifecycleHooks:
    def test_startup_hook(self):
        app = Rivex()

        @app.on_event("startup")
        async def startup():
            pass

        assert len(app._startup_hooks) == 1

    def test_shutdown_hook(self):
        app = Rivex()

        @app.on_event("shutdown")
        async def shutdown():
            pass

        assert len(app._shutdown_hooks) == 1

    def test_multiple_hooks(self):
        app = Rivex()

        @app.on_event("startup")
        async def s1():
            pass

        @app.on_event("startup")
        async def s2():
            pass

        assert len(app._startup_hooks) == 2

    def test_sync_hooks_executed(self):
        app = Rivex()
        calls = []

        @app.on_event("startup")
        def on_start():
            calls.append("started")

        app._run_hooks(app._startup_hooks)
        assert calls == ["started"]


# -- Test: Router Nesting --


class TestRouterNesting:
    def test_nested_prefix(self):
        app = Rivex()
        v1 = Router(prefix="/api/v1")
        users = Router(prefix="/users")

        @users.get("/{user_id}")
        async def get_user(user_id: int):
            return {"id": user_id}

        v1.include_router(users)
        app.include_router(v1)

        paths = [r.path for r in app._routes]
        assert "/api/v1/users/{user_id}" in paths

    def test_all_methods_registered(self):
        app = Rivex()

        @app.get("/g")
        async def g():
            pass

        @app.post("/p")
        async def p():
            pass

        @app.put("/pu")
        async def pu():
            pass

        @app.delete("/d")
        async def d():
            pass

        @app.patch("/pa")
        async def pa():
            pass

        @app.head("/h")
        async def h():
            pass

        @app.options("/o")
        async def o():
            pass

        methods = {r.method for r in app._routes}
        assert methods == {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

    def test_router_tags_propagate(self):
        app = Rivex()
        router = Router(prefix="/v1", tags=["v1"])

        @router.get("/items", tags=["items"])
        async def items():
            return []

        app.include_router(router)
        r = app._routes[0]
        assert "v1" in r.tags
        assert "items" in r.tags

    def test_deep_nesting(self):
        app = Rivex()
        api = Router(prefix="/api")
        v2 = Router(prefix="/v2")
        admin = Router(prefix="/admin")

        @admin.get("/stats")
        async def stats():
            return {}

        v2.include_router(admin)
        api.include_router(v2)
        app.include_router(api)

        paths = [r.path for r in app._routes]
        assert "/api/v2/admin/stats" in paths


# -- Test: Handler Wrapper End-to-End --


class TestHandlerWrapperE2E:
    @pytest.mark.asyncio
    async def test_path_and_query_params(self):
        async def handler(name: str, age: int = 25):
            return {"name": name, "age": age}

        wrapper = build_handler_wrapper(handler, "/users/{name}", 200, False)
        result = await wrapper(
            {
                "method": "GET",
                "path": "/users/alice",
                "path_params": {"name": "alice"},
                "query_string": "age=30",
                "headers": [],
                "body": b"",
            }
        )
        assert result["status"] == 200
        body = _json_body(result)
        assert body["name"] == "alice"
        assert body["age"] == 30

    @pytest.mark.asyncio
    async def test_body_model_deserialization(self):
        async def handler(user: UserCreate):
            return {"name": user.name, "email": user.email, "age": user.age}

        wrapper = build_handler_wrapper(handler, "/users", 201, False)
        result = await wrapper(
            {
                "method": "POST",
                "path": "/users",
                "path_params": {},
                "query_string": "",
                "headers": [("content-type", "application/json")],
                "body": b'{"name": "Bob", "email": "bob@test.com", "age": 30}',
            }
        )
        assert result["status"] == 201
        body = _json_body(result)
        assert body["name"] == "Bob"
        assert body["age"] == 30

    @pytest.mark.asyncio
    async def test_http_exception_in_handler(self):
        async def handler(user_id: int):
            raise HTTPException(404, detail="User not found")

        wrapper = build_handler_wrapper(handler, "/users/{user_id}", 200, False)
        result = await wrapper(
            {
                "method": "GET",
                "path": "/users/999",
                "path_params": {"user_id": "999"},
                "query_string": "",
                "headers": [],
                "body": b"",
            }
        )
        assert result["status"] == 404
        body = json.loads(result["body"])
        assert body["detail"] == "User not found"

    @pytest.mark.asyncio
    async def test_sync_handler(self):
        def handler(x: int = 1):
            return {"value": x * 2}

        wrapper = build_handler_wrapper(handler, "/double", 200, False)
        result = await wrapper(
            {
                "method": "GET",
                "path": "/double",
                "path_params": {},
                "query_string": "x=5",
                "headers": [],
                "body": b"",
            }
        )
        assert result["status"] == 200
        body = _json_body(result)
        assert body["value"] == 10

    @pytest.mark.asyncio
    async def test_missing_required_query_param(self):
        async def handler(q: str):
            return {"q": q}

        wrapper = build_handler_wrapper(handler, "/search", 200, False)
        result = await wrapper(
            {
                "method": "GET",
                "path": "/search",
                "path_params": {},
                "query_string": "",
                "headers": [],
                "body": b"",
            }
        )
        assert result["status"] == 422
        body = json.loads(result["body"])
        detail = body["detail"]
        if isinstance(detail, list):
            assert any("q" in str(e) for e in detail)
        else:
            assert "q" in detail

    @pytest.mark.asyncio
    async def test_handler_returning_response_object(self):
        async def handler():
            return JSONResponse({"custom": True}, status_code=201)

        wrapper = build_handler_wrapper(handler, "/custom", 200, False)
        result = await wrapper(
            {
                "method": "GET",
                "path": "/custom",
                "path_params": {},
                "query_string": "",
                "headers": [],
                "body": b"",
            }
        )
        assert result["status"] == 201
        body = json.loads(result["body"])
        assert body["custom"] is True

    @pytest.mark.asyncio
    async def test_handler_returning_none(self):
        async def handler():
            return None

        wrapper = build_handler_wrapper(handler, "/void", 204, False)
        result = await wrapper(
            {
                "method": "DELETE",
                "path": "/void",
                "path_params": {},
                "query_string": "",
                "headers": [],
                "body": b"",
            }
        )
        assert result["status"] == 204
        assert result["body"] == b""

    @pytest.mark.asyncio
    async def test_custom_exception_handler(self):
        async def handle_value_error(request, exc):
            return JSONResponse({"error": str(exc)}, status_code=422)

        exc_handlers = {ValueError: handle_value_error}

        async def handler():
            raise ValueError("bad value")

        wrapper = build_handler_wrapper(handler, "/fail", 200, False, exc_handlers)
        result = await wrapper(
            {
                "method": "GET",
                "path": "/fail",
                "path_params": {},
                "query_string": "",
                "headers": [],
                "body": b"",
            }
        )
        assert result["status"] == 422
        assert b"bad value" in result["body"]

    @pytest.mark.asyncio
    async def test_unhandled_exception_500(self):
        async def handler():
            raise RuntimeError("unexpected")

        wrapper = build_handler_wrapper(handler, "/crash", 200, False)
        result = await wrapper(
            {
                "method": "GET",
                "path": "/crash",
                "path_params": {},
                "query_string": "",
                "headers": [],
                "body": b"",
            }
        )
        assert result["status"] == 500

    @pytest.mark.asyncio
    async def test_debug_mode_shows_detail(self):
        async def handler():
            raise RuntimeError("debug info")

        wrapper = build_handler_wrapper(handler, "/crash", 200, True)
        result = await wrapper(
            {
                "method": "GET",
                "path": "/crash",
                "path_params": {},
                "query_string": "",
                "headers": [],
                "body": b"",
            }
        )
        assert result["status"] == 500
        body = json.loads(result["body"])
        assert "debug info" in body["detail"]


# -- Test: CORS Middleware Logic --


class TestCORSMiddlewareLogic:
    @pytest.mark.asyncio
    async def test_preflight_request(self):
        mw = CORSMiddleware(allow_origins=["*"])

        async def next_handler(req):
            return {"status": 200, "headers": [], "body": b"ok"}

        result = await mw.process(
            {"method": "OPTIONS", "headers": [("origin", "http://localhost:3000")]},
            next_handler,
        )
        assert result["status"] == 204
        header_dict = dict(result["headers"])
        assert header_dict["access-control-allow-origin"] == "*"

    @pytest.mark.asyncio
    async def test_cors_headers_added_to_response(self):
        mw = CORSMiddleware(allow_origins=["*"])

        async def next_handler(req):
            return {"status": 200, "headers": [("content-type", "application/json")], "body": b"{}"}

        result = await mw.process(
            {"method": "GET", "headers": [("origin", "http://example.com")]},
            next_handler,
        )
        assert result["status"] == 200
        header_keys = [k for k, _ in result["headers"]]
        assert "access-control-allow-origin" in header_keys

    @pytest.mark.asyncio
    async def test_cors_specific_origin(self):
        mw = CORSMiddleware(allow_origins=["http://allowed.com"])

        async def next_handler(req):
            return {"status": 200, "headers": [], "body": b"ok"}

        result = await mw.process(
            {"method": "GET", "headers": [("origin", "http://allowed.com")]},
            next_handler,
        )
        header_dict = dict(result["headers"])
        assert header_dict["access-control-allow-origin"] == "http://allowed.com"

    def test_credentials_with_wildcard_methods_warns(self):
        """The CORS spec forbids ``*`` with credentials; we warn at init."""
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            CORSMiddleware(
                allow_origins=["http://app"],
                allow_methods=["*"],
                allow_credentials=True,
            )
        messages = [str(w.message) for w in caught]
        assert any("allow_credentials=True" in m for m in messages)
        assert any("allow_methods" in m for m in messages)

    @pytest.mark.asyncio
    async def test_credentials_with_wildcard_methods_expanded_at_preflight(self):
        """Wildcard ``*`` must be expanded to a real method list in the
        preflight response so Chrome accepts it under credentials."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mw = CORSMiddleware(
                allow_origins=["http://app"],
                allow_methods=["*"],
                allow_headers=["*"],
                allow_credentials=True,
            )

        async def next_handler(req):
            return {"status": 200, "headers": [], "body": b"ok"}

        result = await mw.process(
            {
                "method": "OPTIONS",
                "headers": [
                    ("origin", "http://app"),
                    ("access-control-request-method", "POST"),
                    ("access-control-request-headers", "content-type, x-csrf-token"),
                ],
            },
            next_handler,
        )
        headers = dict(result["headers"])
        # Star must not appear — the spec forbids it with credentials.
        assert "*" not in headers.get("access-control-allow-methods", "")
        assert "*" not in headers.get("access-control-allow-headers", "")
        assert "POST" in headers["access-control-allow-methods"]
        assert "content-type" in headers["access-control-allow-headers"]
        assert "x-csrf-token" in headers["access-control-allow-headers"]
        assert headers["access-control-allow-credentials"] == "true"
