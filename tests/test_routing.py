from rivex.web.routing import Controller, Router, RouteRecord, get, post, route


def test_router_creates_records():
    router = Router(prefix="/api", tags=["api"])

    @router.get("/items", tags=["items"])
    async def list_items():
        return []

    assert len(router._routes) == 1
    record = router._routes[0]
    assert record.method == "GET"
    assert record.path == "/api/items"
    assert record.tags == ["api", "items"]
    assert record.endpoint is list_items


def test_router_all_methods():
    router = Router()

    @router.get("/r")
    async def g():
        pass

    @router.post("/r")
    async def p():
        pass

    @router.put("/r")
    async def pu():
        pass

    @router.delete("/r")
    async def d():
        pass

    @router.patch("/r")
    async def pa():
        pass

    @router.head("/r")
    async def h():
        pass

    @router.options("/r")
    async def o():
        pass

    methods = [r.method for r in router._routes]
    assert methods == ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


def test_router_metadata():
    router = Router()

    @router.get(
        "/test",
        status_code=201,
        summary="A test",
        description="Detailed",
        operation_id="testOp",
        deprecated=True,
        include_in_schema=False,
    )
    async def handler():
        return {}

    r = router._routes[0]
    assert r.status_code == 201
    assert r.summary == "A test"
    assert r.description == "Detailed"
    assert r.operation_id == "testOp"
    assert r.deprecated is True
    assert r.include_in_schema is False


def test_router_prefix_applied():
    router = Router(prefix="/v1")

    @router.get("/users")
    async def users():
        return []

    assert router._routes[0].path == "/v1/users"


def test_router_tags_merged():
    router = Router(tags=["base"])

    @router.get("/a", tags=["extra"])
    async def a():
        return {}

    @router.get("/b")
    async def b():
        return {}

    assert router._routes[0].tags == ["base", "extra"]
    assert router._routes[1].tags == ["base"]


def test_decorator_returns_original_function():
    router = Router()

    @router.get("/test")
    async def handler():
        return {}

    assert handler.__name__ == "handler"


def test_route_record_defaults():
    async def ep():
        pass

    r = RouteRecord(method="GET", path="/", endpoint=ep)
    assert r.status_code == 200
    assert r.response_model is None
    assert r.tags == []
    assert r.summary is None
    assert r.description is None
    assert r.operation_id is None
    assert r.deprecated is False
    assert r.include_in_schema is True


def test_controller_class_creates_bound_route_records():
    class UsersController(Controller):
        path = "/users"
        tags = ["users"]

        @get("/{user_id}", summary="Get user")
        async def get_user(self, user_id: int):
            return {"id": user_id, "controller": self.__class__.__name__}

        @post("/", status_code=201, tags=["write"])
        async def create_user(self):
            return {"ok": True}

    router = Router()
    router.include_controller(UsersController)

    assert [(r.method, r.path) for r in router._routes] == [
        ("GET", "/users/{user_id}"),
        ("POST", "/users"),
    ]
    assert router._routes[0].tags == ["users"]
    assert router._routes[0].summary == "Get user"
    assert router._routes[1].status_code == 201
    assert router._routes[1].tags == ["users", "write"]
    assert router._routes[0].endpoint.__self__.__class__ is UsersController


def test_route_namespace_attributes_match_bare_decorators():
    # ``route.get`` / ``route.post`` / ... are the same decorators as the bare
    # ``get`` / ``post`` module functions.
    assert route.get is get
    assert route.post is post
    for verb in ("get", "post", "put", "delete", "patch", "head", "options"):
        assert callable(getattr(route, verb))


def test_controller_verb_named_handlers_via_route_namespace():
    # A Controller can name handlers after HTTP verbs when using @route.get,
    # including two same-verb routes — which is impossible with a bare
    # ``from rivex import get`` because ``def get(self): ...`` rebinds ``get``
    # in the class body and the next ``@get(...)`` raises TypeError.
    class ItemController(Controller):
        path = "/items"

        @route.get("")
        async def get(self):
            return {"list": True}

        @route.get("/{item_id}")
        async def get_one(self, item_id: int):
            return {"id": item_id}

    router = Router()
    router.include_controller(ItemController)
    assert [(r.method, r.path) for r in router._routes] == [
        ("GET", "/items"),
        ("GET", "/items/{item_id}"),
    ]


def test_controller_instance_keeps_state():
    class CounterController(Controller):
        path = "/counter"

        def __init__(self):
            self.value = 7

        @get("/")
        def read(self):
            return {"value": self.value}

    controller = CounterController()
    router = Router()
    router.include_router(controller)

    assert router._routes[0].path == "/counter"
    assert router._routes[0].endpoint() == {"value": 7}


def test_controller_include_prefix_and_tags_merge():
    class AdminController(Controller):
        path = "/users"
        tags = ["users"]

        @get("/")
        async def list_users(self):
            return []

    router = Router(prefix="/api", tags=["api"])
    router.include_controller(AdminController, prefix="/admin", tags=["admin"])

    route = router._routes[0]
    assert route.path == "/api/admin/users"
    assert route.tags == ["api", "admin", "users"]
