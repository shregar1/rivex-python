from pydantic import BaseModel

from rivex.applications.applications import Rivex
from rivex.di.dependencies import Depends
from rivex.openapi.openapi import generate_openapi
from rivex.di.params import Path
from rivex.web.routing import Controller, RouteRecord, get, post, put, patch, delete
from rivex.auth.security import APIKeyHeader, OAuth2PasswordBearer


def test_basic_spec_structure():
    spec = generate_openapi(title="Test API", version="1.0.0", routes=[])
    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["title"] == "Test API"
    assert spec["info"]["version"] == "1.0.0"


def test_description():
    spec = generate_openapi(title="Test", version="1.0", description="A test API", routes=[])
    assert spec["info"]["description"] == "A test API"


def test_path_parameters():
    async def greet(name: str):
        return {"message": f"Hello, {name}!"}

    routes = [RouteRecord(method="GET", path="/hello/{name}", endpoint=greet)]
    spec = generate_openapi(title="T", version="1", routes=routes)

    op = spec["paths"]["/hello/{name}"]["get"]
    assert len(op["parameters"]) == 1
    p = op["parameters"][0]
    assert p["name"] == "name"
    assert p["in"] == "path"
    assert p["required"] is True
    assert p["schema"]["type"] == "string"


def test_query_parameters():
    async def search(q: str, limit: int = 10, active: bool = True):
        return []

    routes = [RouteRecord(method="GET", path="/search", endpoint=search)]
    spec = generate_openapi(title="T", version="1", routes=routes)

    op = spec["paths"]["/search"]["get"]
    params = {p["name"]: p for p in op["parameters"]}

    assert params["q"]["required"] is True
    assert params["q"]["schema"]["type"] == "string"
    assert params["limit"]["required"] is False
    assert params["limit"]["schema"]["default"] == 10
    assert params["active"]["schema"]["type"] == "boolean"


def test_pydantic_request_body():
    class UserCreate(BaseModel):
        name: str
        email: str

    async def create_user(user: UserCreate):
        return {"id": 1}

    routes = [RouteRecord(method="POST", path="/users", endpoint=create_user, status_code=201)]
    spec = generate_openapi(title="T", version="1", routes=routes)

    op = spec["paths"]["/users"]["post"]
    assert "requestBody" in op
    ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/UserCreate"
    assert "UserCreate" in spec["components"]["schemas"]
    props = spec["components"]["schemas"]["UserCreate"]["properties"]
    assert "name" in props
    assert "email" in props


def test_response_model():
    class Item(BaseModel):
        id: int
        name: str

    async def get_item(item_id: int):
        return Item(id=item_id, name="Widget")

    routes = [
        RouteRecord(
            method="GET",
            path="/items/{item_id}",
            endpoint=get_item,
            response_model=Item,
        )
    ]
    spec = generate_openapi(title="T", version="1", routes=routes)

    op = spec["paths"]["/items/{item_id}"]["get"]
    resp = op["responses"]["200"]
    ref = resp["content"]["application/json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/Item"


def test_tags():
    async def list_users():
        return []

    routes = [
        RouteRecord(method="GET", path="/users", endpoint=list_users, tags=["users", "admin"])
    ]
    spec = generate_openapi(title="T", version="1", routes=routes)

    op = spec["paths"]["/users"]["get"]
    assert op["tags"] == ["users", "admin"]
    tag_names = [t["name"] for t in spec["tags"]]
    assert "admin" in tag_names
    assert "users" in tag_names


def test_summary_and_description():
    async def handler():
        return {}

    routes = [
        RouteRecord(
            method="GET",
            path="/test",
            endpoint=handler,
            summary="Test endpoint",
            description="This is a detailed description",
        )
    ]
    spec = generate_openapi(title="T", version="1", routes=routes)

    op = spec["paths"]["/test"]["get"]
    assert op["summary"] == "Test endpoint"
    assert op["description"] == "This is a detailed description"


def test_docstring_as_summary():
    async def handler():
        """Get the thing."""
        return {}

    routes = [RouteRecord(method="GET", path="/test", endpoint=handler)]
    spec = generate_openapi(title="T", version="1", routes=routes)

    op = spec["paths"]["/test"]["get"]
    assert op["summary"] == "Get the thing."


def test_operation_id():
    async def handler():
        return {}

    routes = [
        RouteRecord(
            method="GET",
            path="/test",
            endpoint=handler,
            operation_id="customOpId",
        )
    ]
    spec = generate_openapi(title="T", version="1", routes=routes)
    assert spec["paths"]["/test"]["get"]["operationId"] == "customOpId"


def test_auto_operation_id():
    async def my_endpoint():
        return {}

    routes = [RouteRecord(method="GET", path="/test", endpoint=my_endpoint)]
    spec = generate_openapi(title="T", version="1", routes=routes)
    assert spec["paths"]["/test"]["get"]["operationId"] == "my_endpoint_test_get"


def test_deprecated():
    async def old():
        return {}

    routes = [RouteRecord(method="GET", path="/old", endpoint=old, deprecated=True)]
    spec = generate_openapi(title="T", version="1", routes=routes)
    assert spec["paths"]["/old"]["get"]["deprecated"] is True


def test_exclude_from_schema():
    async def internal():
        return {}

    routes = [
        RouteRecord(method="GET", path="/internal", endpoint=internal, include_in_schema=False)
    ]
    spec = generate_openapi(title="T", version="1", routes=routes)
    assert "paths" not in spec or "/internal" not in spec.get("paths", {})


def test_depends_excluded_from_params():
    def get_db():
        return "db"

    async def handler(db: str = Depends(get_db), q: str = ""):
        return {}

    routes = [RouteRecord(method="GET", path="/test", endpoint=handler)]
    spec = generate_openapi(title="T", version="1", routes=routes)

    op = spec["paths"]["/test"]["get"]
    param_names = [p["name"] for p in op.get("parameters", [])]
    assert "db" not in param_names
    assert "q" in param_names


def test_multiple_methods_same_path():
    async def get_items():
        return []

    async def create_item():
        return {}

    routes = [
        RouteRecord(method="GET", path="/items", endpoint=get_items),
        RouteRecord(method="POST", path="/items", endpoint=create_item, status_code=201),
    ]
    spec = generate_openapi(title="T", version="1", routes=routes)

    assert "get" in spec["paths"]["/items"]
    assert "post" in spec["paths"]["/items"]
    assert (
        spec["paths"]["/items"]["post"]["responses"]["201"]["description"] == "Successful response"
    )


def test_docs_html_uses_custom_minimal_ui(monkeypatch):
    # The standalone fallback HTML has no swagger-ui / cdn dependencies.
    # The ``rivex_react`` package ships a prebuilt React app that pulls
    # Monaco from jsDelivr, which is *fine* in production but not what
    # this test is asserting — the test pins the "minimal UI" contract
    # so we exercise the fallback path by blocking the React import
    # just for the duration of the assertion.
    import builtins as _builtins
    import importlib

    real_import = _builtins.__import__

    def _guarded_import(name, *args, **kwargs):
        if name == "rivex_react" or name.startswith("rivex_react."):
            raise ImportError(f"blocked: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(_builtins, "__import__", _guarded_import)
    # Reload the openapi module so the try/except ImportError
    # in ``build_docs_html`` re-evaluates against the blocked import.
    from rivex import openapi as _openapi

    importlib.reload(_openapi)
    try:
        html = _openapi.build_docs_html("Demo API", "/openapi.json")
    finally:
        # Restore the real openapi module so later tests see it as
        # originally imported.
        importlib.reload(_openapi)

    assert "Demo API" in html
    assert "/openapi.json" in html
    assert "swagger-ui" not in html
    assert "cdn.jsdelivr" not in html


def test_openapi_metadata_customization():
    spec = generate_openapi(
        title="T",
        version="1",
        routes=[],
        servers=[{"url": "https://api.example.com"}],
        terms_of_service="https://example.com/terms",
        contact={"email": "team@example.com"},
        license_info={"name": "MIT"},
        openapi_tags=[{"name": "users", "description": "User operations"}],
    )

    assert spec["servers"] == [{"url": "https://api.example.com"}]
    assert spec["info"]["termsOfService"] == "https://example.com/terms"
    assert spec["info"]["contact"]["email"] == "team@example.com"
    assert spec["info"]["license"]["name"] == "MIT"
    assert spec["tags"] == [{"name": "users", "description": "User operations"}]


def test_openapi_security_schemes_from_dependencies():
    api_key = APIKeyHeader(name="x-api-key", scheme_name="APIKeyAuth")
    oauth2 = OAuth2PasswordBearer(tokenUrl="/token", scheme_name="OAuth2")

    async def secure(key: str = Depends(api_key), token: str = Depends(oauth2)):
        return {"ok": True}

    routes = [RouteRecord(method="GET", path="/secure", endpoint=secure)]
    spec = generate_openapi(title="T", version="1", routes=routes)

    schemes = spec["components"]["securitySchemes"]
    assert schemes["APIKeyAuth"] == {"type": "apiKey", "in": "header", "name": "x-api-key"}
    assert schemes["OAuth2"]["type"] == "oauth2"
    assert spec["paths"]["/secure"]["get"]["security"] == [
        {"APIKeyAuth": []},
        {"OAuth2": []},
    ]


def test_openapi_extra_merges_into_operation():
    async def handler():
        return {"ok": True}

    routes = [
        RouteRecord(
            method="GET",
            path="/x",
            endpoint=handler,
            openapi_extra={"x-codeSamples": [{"lang": "Python", "source": "pass"}]},
        )
    ]
    spec = generate_openapi(title="T", version="1", routes=routes)

    assert spec["paths"]["/x"]["get"]["x-codeSamples"][0]["lang"] == "Python"


# ---------------------------------------------------------------------------
# Class-based controllers — make sure their handlers reach the OpenAPI spec
# ---------------------------------------------------------------------------


def test_class_controller_routes_appear_in_openapi_spec():
    """Handlers declared on a ``Controller`` subclass and mounted via
    ``app.include_controller()`` must show up under their full path
    (prefix + path) in the generated spec — verifying the user-facing
    documentation pipeline works end-to-end for class controllers."""

    class WidgetsController(Controller):
        path = "/api/v1/widgets"
        tags = ["widgets"]

        @get("", summary="List widgets")
        async def list_widgets(self):
            return []

        @get("/{widget_id}", summary="Get a widget")
        async def get_widget(self, widget_id: int = Path(ge=1)):
            return {"id": widget_id}

        @post("/{widget_id}/archive", summary="Archive a widget")
        async def archive_widget(self, widget_id: int = Path(ge=1)):
            return {"archived": widget_id}

    app = Rivex(title="ArchX-like", version="1.0.0")
    app.include_controller(WidgetsController)

    spec = generate_openapi(title=app.title, version=app.version, routes=app._routes)

    paths = spec.get("paths", {})
    assert "/api/v1/widgets" in paths
    assert "get" in paths["/api/v1/widgets"]
    assert paths["/api/v1/widgets"]["get"]["summary"] == "List widgets"

    assert "/api/v1/widgets/{widget_id}" in paths
    assert paths["/api/v1/widgets/{widget_id}"]["get"]["summary"] == "Get a widget"

    assert "/api/v1/widgets/{widget_id}/archive" in paths
    assert paths["/api/v1/widgets/{widget_id}/archive"]["post"]["summary"] == "Archive a widget"

    # Tags from the Controller class should flow into the spec.
    list_tags = paths["/api/v1/widgets"]["get"].get("tags", [])
    assert "widgets" in list_tags


# ---------------------------------------------------------------------------
# Full CRUD on the same path — every method must survive route collection
# and the OpenAPI emitter must publish every one of them.
# ---------------------------------------------------------------------------


def test_full_crud_on_collection_and_item_paths_emits_all_methods():
    """Pin the contract that POST/PATCH/DELETE reach the spec alongside the
    GETs on both the collection (``/widgets``) and item (``/widgets/{id}``)
    paths. Regression guard for a class of bugs where a controller template
    drops the mutation decorators and/or routes them at literal paths so
    the OpenAPI emitter only sees the lookup (GET) subset."""

    class WidgetsController(Controller):
        path = "/api/v1/widgets"
        tags = ["widgets"]

        @get("", summary="List widgets")
        async def list_widgets(self):
            return []

        @post("", summary="Create a widget")
        async def create_widget(self):
            return {}

        @get("/{widget_id}", summary="Fetch a widget")
        async def get_widget(self, widget_id: int):
            return {}

        @patch("/{widget_id}", summary="Update a widget")
        async def update_widget(self, widget_id: int):
            return {}

        @delete("/{widget_id}", summary="Delete a widget")
        async def delete_widget(self, widget_id: int):
            return {}

    app = Rivex(title="CRUD", version="1.0.0")
    app.include_controller(WidgetsController)

    spec = generate_openapi(title=app.title, version=app.version, routes=app._routes)
    paths = spec.get("paths", {})

    assert set(paths["/api/v1/widgets"].keys()) == {"get", "post"}
    assert set(paths["/api/v1/widgets/{widget_id}"].keys()) == {"get", "patch", "delete"}


def test_many_controllers_with_mutations_does_not_drop_methods():
    """Bigger-scale regression: 11 controllers with 3 mutations each + 73
    controllers with 6 mutations each, totalling >400 mutation routes, must
    all show up in the emitted spec. Guards against any future emitter
    change that silently filters non-GET methods at scale."""

    app = Rivex(title="MegaApp", version="1.0.0")

    def _make_controller(cls_name: str, path: str, mutations: list[str]) -> type:
        attrs = {
            "path": path,
            "tags": [path.strip("/").split("/")[-1]],
            "__module__": "__main__",
        }
        if "list" in mutations:
            attrs["list_items"] = _route(get, "", "list")
        if "create" in mutations:
            attrs["create_item"] = _route(post, "", "create")
        if "bulk_create" in mutations:
            attrs["bulk_create"] = _route(post, "/bulk", "bulk_create")
        if "retrieve" in mutations:
            attrs["get_item"] = _route(get, "/{item_id}", "get")
        if "replace" in mutations:
            attrs["replace_item"] = _route(put, "/{item_id}", "put")
        if "update" in mutations:
            attrs["update_item"] = _route(patch, "/{item_id}", "patch")
        if "destroy" in mutations:
            attrs["delete_item"] = _route(delete, "/{item_id}", "delete")
        if "bulk_delete" in mutations:
            attrs["bulk_delete"] = _route(delete, "/bulk", "bulk_delete")
        return type(cls_name, (Controller,), attrs)

    def _route(decorator, path, name):
        async def handler(self, *args, **kwargs):
            return {}
        handler.__name__ = name
        return decorator(path, summary=name)(handler)

    for i in range(11):
        app.include_controller(
            _make_controller(
                f"NewSlice{i}",
                f"/api/v1/new_slice_{i}",
                ["list", "create", "update", "destroy"],
            )
        )
    for i in range(73):
        app.include_controller(
            _make_controller(
                f"ExistingSlice{i}",
                f"/api/v1/existing_slice_{i}",
                [
                    "list",
                    "retrieve",
                    "create",
                    "bulk_create",
                    "replace",
                    "update",
                    "destroy",
                    "bulk_delete",
                ],
            )
        )

    mutation_count = sum(1 for r in app._routes if r.method != "GET")
    assert mutation_count > 400, f"expected >400 mutation routes, got {mutation_count}"

    spec = generate_openapi(title=app.title, version=app.version, routes=app._routes)
    methods_in_spec: set[str] = set()
    for ops in spec["paths"].values():
        methods_in_spec.update(ops.keys())

    assert {"get", "post", "patch", "delete", "put"} <= methods_in_spec, (
        f"missing methods in spec: {methods_in_spec}"
    )

    # Spot-check: at least one POST/PATCH/DELETE/PUT must reach each path
    # that also has a GET, not just exist somewhere in the spec.
    for path, ops in spec["paths"].items():
        if "get" in ops and "{item_id}" in path:
            assert {"get", "patch", "delete"} <= ops.keys(), (
                f"{path} is missing mutations: {sorted(ops.keys())}"
            )

