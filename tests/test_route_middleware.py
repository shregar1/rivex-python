"""Per-route middleware tests.

Middleware can be attached to individual routes via the
``middleware=[...]`` kwarg on ``@app.get(...)``, ``@router.get(...)``,
route groups, and controller method decorators. Entries are either
``(MiddlewareClass, kwargs)`` tuples or bare middleware classes.
"""

from rivex import Rivex, Router
from rivex.web.routing import Controller, route
from rivex.middleware.abstraction import Middleware
from rivex.testing.testing import TestClient


class HeaderMiddleware(Middleware):
    def __init__(self, name: str = "x-mw", value: str = "on"):
        self.name = name
        self.value = value

    async def process(self, request_data, call_next):
        resp = await call_next(request_data)
        resp.setdefault("headers", []).append((self.name, self.value))
        return resp


class BlockMiddleware(Middleware):
    def __init__(self, status: int = 403):
        self.status = status

    async def process(self, request_data, call_next):
        return {"status": self.status, "headers": [], "body": b"blocked"}


def test_app_route_middleware_tuple_form():
    app = Rivex()

    @app.get("/tagged", middleware=[(HeaderMiddleware, {"value": "route"})])
    async def tagged():
        return {"ok": True}

    @app.get("/plain")
    async def plain():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/tagged")
    assert resp.status_code == 200
    assert resp.headers["x-mw"] == "route"

    resp = client.get("/plain")
    assert resp.status_code == 200
    assert "x-mw" not in resp.headers


def test_app_route_middleware_bare_class():
    app = Rivex()

    @app.get("/tagged", middleware=[HeaderMiddleware])
    async def tagged():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/tagged")
    assert resp.headers["x-mw"] == "on"


def test_app_route_middleware_short_circuits():
    app = Rivex()

    @app.get("/blocked", middleware=[(BlockMiddleware, {"status": 401})])
    async def blocked():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/blocked")
    assert resp.status_code == 401
    assert resp.text == "blocked"


def test_router_route_middleware_merges_with_router_level():
    app = Rivex()
    router = Router(prefix="/api")
    router.add_middleware(HeaderMiddleware, name="x-router", value="1")

    @router.get("/users", middleware=[(HeaderMiddleware, {"name": "x-route", "value": "2"})])
    async def users():
        return {"users": []}

    @router.get("/items")
    async def items():
        return {"items": []}

    app.include_router(router)

    client = TestClient(app)
    resp = client.get("/api/users")
    assert resp.headers["x-router"] == "1"
    assert resp.headers["x-route"] == "2"

    resp = client.get("/api/items")
    assert resp.headers["x-router"] == "1"
    assert "x-route" not in resp.headers


def test_route_group_middleware_kwarg_still_works():
    app = Rivex()

    with app.group(prefix="/g", middleware=[(HeaderMiddleware, {"value": "group"})]) as grp:

        @grp.get("/a")
        async def a():
            return {"ok": True}

        @grp.get("/b", middleware=[(HeaderMiddleware, {"name": "x-route", "value": "b"})])
        async def b():
            return {"ok": True}

    client = TestClient(app)
    resp = client.get("/g/a")
    assert resp.headers["x-mw"] == "group"
    assert "x-route" not in resp.headers

    resp = client.get("/g/b")
    assert resp.headers["x-mw"] == "group"
    assert resp.headers["x-route"] == "b"


def test_controller_method_middleware():
    class Ctrl(Controller):
        path = "/ctrl"

        @route.get("/tagged", middleware=[(HeaderMiddleware, {"value": "ctrl"})])
        async def tagged(self):
            return {"ok": True}

    app = Rivex()
    app.include_controller(Ctrl)

    client = TestClient(app)
    resp = client.get("/ctrl/tagged")
    assert resp.status_code == 200
    assert resp.headers["x-mw"] == "ctrl"


def test_invalid_middleware_entry_raises():
    app = Rivex()

    try:

        @app.get("/bad", middleware=["not-a-middleware"])
        async def bad():
            return {"ok": True}

    except TypeError:
        return
    raise AssertionError("expected TypeError for invalid middleware entry")
