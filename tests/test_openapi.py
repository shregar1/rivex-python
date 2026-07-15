from pydantic import BaseModel

from rivex.core.applications import Rivex
from rivex.core.dependencies import Depends
from rivex.openapi.openapi import generate_openapi
from rivex.core.params import Path
from rivex.core.routing import Controller, RouteRecord, get, post
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
    api_key = APIKeyHeader(name="x-api-key", scheme_name="ApiKeyAuth")
    oauth2 = OAuth2PasswordBearer(tokenUrl="/token", scheme_name="OAuth2")

    async def secure(key: str = Depends(api_key), token: str = Depends(oauth2)):
        return {"ok": True}

    routes = [RouteRecord(method="GET", path="/secure", endpoint=secure)]
    spec = generate_openapi(title="T", version="1", routes=routes)

    schemes = spec["components"]["securitySchemes"]
    assert schemes["ApiKeyAuth"] == {"type": "apiKey", "in": "header", "name": "x-api-key"}
    assert schemes["OAuth2"]["type"] == "oauth2"
    assert spec["paths"]["/secure"]["get"]["security"] == [
        {"ApiKeyAuth": []},
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

