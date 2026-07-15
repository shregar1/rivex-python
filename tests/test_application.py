import json

import pytest

from rivex import Controller, HTTPException, Rivex, Router, get
from rivex.core._injection import build_handler_wrapper
from rivex.core.responses import JSONResponse


def test_app_init_defaults():
    app = Rivex()
    assert app.title == "Rivex"
    assert app.version == "0.1.0"
    assert app.debug is False
    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"


def test_app_init_custom():
    app = Rivex(
        title="My API",
        version="2.0",
        description="A custom API",
        debug=True,
        docs_url="/api-docs",
        openapi_url="/api/schema.json",
    )
    assert app.title == "My API"
    assert app.description == "A custom API"
    assert app.docs_url == "/api-docs"


def test_route_registration():
    app = Rivex()

    @app.get("/test")
    async def test_handler():
        return {"ok": True}

    assert len(app._routes) == 1
    assert app._routes[0].method == "GET"
    assert app._routes[0].path == "/test"
    assert app._routes[0].endpoint is test_handler


def test_all_http_methods():
    app = Rivex()

    @app.get("/a")
    async def g():
        pass

    @app.post("/a")
    async def p():
        pass

    @app.put("/a")
    async def pu():
        pass

    @app.delete("/a")
    async def d():
        pass

    @app.patch("/a")
    async def pa():
        pass

    @app.head("/a")
    async def h():
        pass

    @app.options("/a")
    async def o():
        pass

    methods = [r.method for r in app._routes]
    assert methods == ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


def test_route_metadata():
    app = Rivex()

    @app.get(
        "/items",
        status_code=201,
        tags=["items"],
        summary="List items",
        response_model=list,
    )
    async def list_items():
        return []

    r = app._routes[0]
    assert r.status_code == 201
    assert r.tags == ["items"]
    assert r.summary == "List items"
    assert r.response_model is list


def test_include_router():
    app = Rivex()
    router = Router(prefix="/api", tags=["api"])

    @router.get("/items")
    async def items():
        return []

    app.include_router(router, tags=["v1"])

    assert len(app._routes) == 1
    assert app._routes[0].path == "/api/items"
    assert app._routes[0].tags == ["v1", "api"]


def test_include_router_with_prefix():
    app = Rivex()
    router = Router()

    @router.get("/health")
    async def health():
        return {"ok": True}

    app.include_router(router, prefix="/v2")

    assert app._routes[0].path == "/v2/health"


def test_include_controller_class():
    app = Rivex()

    class HealthController(Controller):
        path = "/health"

        @get("/")
        async def check(self):
            return {"ok": True}

    app.include_controller(HealthController)

    assert len(app._routes) == 1
    assert app._routes[0].method == "GET"
    assert app._routes[0].path == "/health"
    assert app._routes[0].endpoint.__self__.__class__ is HealthController


def test_include_controller_via_include_router():
    app = Rivex()

    class ItemsController(Controller):
        path = "/items"
        tags = ["items"]

        @get("/{item_id}")
        def get_item(self, item_id: int):
            return {"id": item_id}

    app.include_router(ItemsController, prefix="/api", tags=["v1"])

    assert len(app._routes) == 1
    route = app._routes[0]
    assert route.path == "/api/items/{item_id}"
    assert route.tags == ["v1", "items"]


def test_on_event_startup():
    app = Rivex()
    called = []

    @app.on_event("startup")
    def on_start():
        called.append("started")

    assert len(app._startup_hooks) == 1
    app._run_hooks(app._startup_hooks)
    assert called == ["started"]


def test_on_event_shutdown():
    app = Rivex()
    called = []

    @app.on_event("shutdown")
    async def on_stop():
        called.append("stopped")

    assert len(app._shutdown_hooks) == 1
    app._run_hooks(app._shutdown_hooks)
    assert called == ["stopped"]


def test_exception_handler_registration():
    app = Rivex()

    @app.exception_handler(ValueError)
    async def handle_ve(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    assert ValueError in app._exception_handlers


@pytest.mark.asyncio
async def test_custom_exception_handler_invoked():
    async def handle_value_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    exc_handlers = {ValueError: handle_value_error}

    async def handler():
        raise ValueError("bad value")

    wrapper = build_handler_wrapper(handler, "/test", 200, False, exc_handlers)
    result = await wrapper(
        {
            "method": "GET",
            "path": "/test",
            "path_params": {},
            "query_string": "",
            "headers": [],
            "body": b"",
        }
    )
    assert result["status"] == 422
    assert b"bad value" in result["body"]


@pytest.mark.asyncio
async def test_http_exception_handler_override():
    async def custom_http_handler(request, exc):
        return JSONResponse(
            {"error": exc.detail, "code": exc.status_code}, status_code=exc.status_code
        )

    exc_handlers = {HTTPException: custom_http_handler}

    async def handler():
        raise HTTPException(404, detail="not here")

    wrapper = build_handler_wrapper(handler, "/test", 200, False, exc_handlers)
    result = await wrapper(
        {
            "method": "GET",
            "path": "/test",
            "path_params": {},
            "query_string": "",
            "headers": [],
            "body": b"",
        }
    )
    assert result["status"] == 404
    body = json.loads(result["body"])
    assert body["error"] == "not here"
    assert body["code"] == 404


def test_add_middleware():
    from rivex import CORSMiddleware

    app = Rivex()
    app.add_middleware(CORSMiddleware, allow_origins=["http://example.com"])

    assert len(app._middleware) == 1
    cls, kwargs = app._middleware[0]
    assert cls is CORSMiddleware
    assert kwargs["allow_origins"] == ["http://example.com"]


@pytest.mark.asyncio
async def test_callable_class_middleware():
    app = Rivex()

    class HeaderMiddleware:
        def __init__(self, value: str):
            self.value = value

        async def __call__(self, request_data, call_next):
            response = await call_next(request_data)
            response["headers"] = response.get("headers", []) + [("x-class-middleware", self.value)]
            return response

    async def handler(request_data):
        return {"status": 200, "headers": [], "body": b"ok"}

    app.add_middleware(HeaderMiddleware, value="enabled")
    wrapped = app._apply_middleware(handler)
    response = await wrapped({"headers": []})

    assert response["headers"] == [("x-class-middleware", "enabled")]


def test_disable_docs():
    app = Rivex(docs_url=None, openapi_url=None)
    assert app.docs_url is None
    assert app.openapi_url is None
