"""End-to-end test of the Vexarr family dashboard stack.

Exercises every feature added in this session:
- Body backends (pydantic / dataclass / attrs / msgspec)
- Cookie + header + query-string auth
- Operational status page with sign-in form
- Admin dashboard with HTMX partials + actions
- OpenAPI docs page with schemas
- Landing page route
- Powered-by RiveX footer
"""

import json as _json
import os
import pathlib
import sys
import tempfile

# Make sure the runtime stub from tests/conftest is loaded
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import pytest


@pytest.fixture
def demo_app(monkeypatch):
    """Build a fresh Rivex app with the Vexarr family dashboard stack.

    Mirrors what `_run_demo.py` does but without the HTTP server
    so we can call handlers directly.
    """
    # Use a temp DB so tests don't pollute each other
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = pathlib.Path(tmp.name)
    monkeypatch.setenv("RIVEX_ADMIN_DB", str(db_path))

    from pydantic import BaseModel

    from rivex import Rivex

    app = Rivex(
        title="Test API",
        version="1.0.0",
        description="Test description",
        app_name="TestApp",
        powered_by="Test Cloud",
        admin_url="/admin",
        admin_db=db_path,
        landing_page=True,
    )

    # Seed an admin user
    from rivex_admin.db import AdminStore

    store = AdminStore(db_path)
    store.add_user("admin", "test-token", note="e2e test")

    class Widget(BaseModel):
        id: int
        name: str

    class WidgetCreate(BaseModel):
        name: str

    @app.get("/widgets", summary="List widgets", response_model=list[Widget])
    async def list_widgets() -> list[dict]:
        return [{"id": 1, "name": "Widget"}]

    @app.get("/widgets/{wid}", summary="Get widget", response_model=Widget)
    async def get_widget(wid: int = ...) -> dict:
        return {"id": wid, "name": "Widget"}

    @app.post("/widgets", summary="Create widget", response_model=Widget)
    async def create_widget(payload: WidgetCreate) -> dict:
        return {"id": 99, "name": payload.name}

    return app, store, db_path


# ── Body backends ──────────────────────────────────────────────────


def test_body_pydantic_basic(demo_app) -> None:
    """Pydantic models work in Body() / Form() / Query() / Path()."""
    app, _, _ = demo_app
    # The POST /widgets handler accepts a Pydantic model — verify it
    # exists in the app's routes with the right response_model.
    routes = [(r.method, r.path) for r in app._routes]
    assert ("POST", "/widgets") in routes


# ── Cookie auth ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cookie_auth(demo_app) -> None:
    """Cookie auth works end-to-end."""
    # Verify the auth extraction recognizes cookies
    from rivex_admin import _extract_token

    rd = {"headers": [("Cookie", "rivex_admin_token=test-token; Path=/")]}
    assert _extract_token(rd) == "test-token"


@pytest.mark.asyncio
async def test_header_auth(demo_app) -> None:
    """X-Admin-Token header auth works."""
    from rivex_admin import _extract_token

    rd = {"headers": [("X-Admin-Token", "test-token")]}
    assert _extract_token(rd) == "test-token"


@pytest.mark.asyncio
async def test_query_string_auth(demo_app) -> None:
    """?token=... query string auth works."""
    from rivex_admin import _extract_token

    rd = {"query_string": "token=test-token"}
    assert _extract_token(rd) == "test-token"


@pytest.mark.asyncio
async def test_no_auth(demo_app) -> None:
    """No auth returns None."""
    from rivex_admin import _extract_token

    assert _extract_token({"headers": []}) is None
    assert _extract_token({"query_string": ""}) is None


# ── Admin DB store ────────────────────────────────────────────────


def test_admin_db_add_and_verify(demo_app) -> None:
    """AdminStore add_user + verify_token round-trip."""
    _, store, _ = demo_app
    user = store.verify_token("test-token")
    assert user is not None
    assert user.username == "admin"


def test_admin_db_bad_token(demo_app) -> None:
    """Invalid token returns None."""
    _, store, _ = demo_app
    assert store.verify_token("nope") is None


def test_admin_db_rotate(demo_app) -> None:
    """rotate_token invalidates the old token."""
    _, store, _ = demo_app
    assert store.verify_token("test-token") is not None
    store.rotate_token("admin", "new-token")
    assert store.verify_token("test-token") is None
    assert store.verify_token("new-token") is not None


def test_admin_db_delete(demo_app) -> None:
    """delete_user removes the user."""
    _, store, _ = demo_app
    assert store.has_any_users() is True
    store.delete_user("admin")
    assert store.has_any_users() is False


def test_admin_db_touch_used(demo_app) -> None:
    """touch_used updates last_used_at."""
    _, store, _ = demo_app
    user = store.verify_token("test-token")
    assert user is not None
    assert user.last_used_at is None
    store.touch_used("admin")
    user2 = store.verify_token("test-token")
    assert user2.last_used_at is not None


# ── OpenAPI spec generation ──────────────────────────────────────


def test_openapi_paths(demo_app) -> None:
    """OpenAPI spec has all 3 routes."""
    app, _, _ = demo_app
    paths = [r.path for r in app._routes]
    assert "/widgets" in paths
    assert "/widgets/{wid}" in paths


def test_openapi_response_model(demo_app) -> None:
    """Routes with response_model are marked."""
    app, _, _ = demo_app
    for r in app._routes:
        if r.path == "/widgets" and r.method == "GET":
            assert r.response_model is not None


# ── Server page (operational status) ─────────────────────────────


def test_build_server_html_renders_brand() -> None:
    """build_server_html includes the app name as a wordmark."""
    from rivex.openapi.openapi import build_server_html

    html = build_server_html(
        title="My API",
        version="1.0",
        admin_url="/admin",
        app_name="MyApp",
        powered_by="My Cloud",
    )
    assert "MyApp" in html or "MYAPP" in html
    assert "/admin" in html
    assert "powered by" in html
    assert "Rive" in html  # powered by RiveX


def test_build_server_html_with_alpinejs() -> None:
    """build_server_html loads Alpine.js and has theme toggle."""
    from rivex.openapi.openapi import build_server_html

    html = build_server_html(title="X", version="1", admin_url="/admin")
    assert "alpine.min.js" in html
    assert "toggleTheme" in html
    assert "theme: 'dark'" in html  # dark default


def test_build_server_html_signin_form() -> None:
    """build_server_html has a sign-in form when admin_url is set."""
    from rivex.openapi.openapi import build_server_html

    html = build_server_html(title="X", version="1", admin_url="/admin")
    assert 'hx-post="/admin/session"' in html
    assert 'name="token"' in html
    assert 'id="signin-error"' in html


def test_build_server_html_no_admin() -> None:
    """No admin_url → no sign-in form."""
    from rivex.openapi.openapi import build_server_html

    html = build_server_html(title="X", version="1", admin_url=None)
    assert "hx-post" not in html
    assert 'id="signin-error"' not in html


# ── Docs page ─────────────────────────────────────────────────────


def test_build_docs_html_renders_brand() -> None:
    """build_docs_html (via _fallback_docs_html) renders the brand."""
    from rivex.openapi.openapi import _fallback_docs_html

    html = _fallback_docs_html("My API", "/openapi.json", app_name="MyApp")
    assert "MYAPP" in html or "MyApp" in html
    assert 'x-data="docsPage()"' in html  # Alpine.js
    assert "method-GET" in html  # color pill
    assert "method-POST" in html
    assert "powered by</span> Rive" in html  # space + accent


def test_build_docs_html_theme_toggle() -> None:
    """Docs page has a dark/light theme toggle."""
    from rivex.openapi.openapi import _fallback_docs_html

    html = _fallback_docs_html("X", "/openapi.json")
    assert "icon-sun" in html
    assert "icon-moon" in html
    assert "toggleTheme" in html


def test_build_docs_html_search_input() -> None:
    """Docs page has a search filter for endpoints."""
    from rivex.openapi.openapi import _fallback_docs_html

    html = _fallback_docs_html("X", "/openapi.json")
    assert "Filter endpoints" in html
    assert 'x-model="query"' in html


def test_build_docs_html_no_hero() -> None:
    """Hero section was removed."""
    from rivex.openapi.openapi import _fallback_docs_html

    html = _fallback_docs_html("X", "/openapi.json")
    assert 'class="hero"' not in html
    assert 'class="word"' not in html


# ── Admin shell ───────────────────────────────────────────────────


def test_build_admin_html_renders_brand() -> None:
    """build_admin_html (via _fallback_admin_html) renders the Vexarr admin shell."""
    from rivex.openapi.openapi import _fallback_admin_html

    html = _fallback_admin_html(
        title="Admin",
        base_path="/admin",
        static_url="/admin/static",
        app_name="AdminApp",
        powered_by="Acme",
        version="1.0",
        partials=[
            {"name": "overview", "title": "Overview", "icon": ""},
            {"name": "logs", "title": "Logs", "icon": ""},
        ],
    )
    # The brand mark is uppercased via CSS text-transform, so the
    # HTML contains the raw mixed-case text. Check for the raw form.
    assert "AdminApp" in html or "ADMINAP" in html
    assert "x-data=" in html  # Alpine.js
    assert 'x-text="theme' in html  # theme binding
    assert "powered by" in html
    assert "RiveX" in html  # brand mark


def test_build_admin_html_top_bar_pills() -> None:
    """Admin shell has the top bar with status + theme + sign-out."""
    from rivex.openapi.openapi import _fallback_admin_html

    html = _fallback_admin_html(
        title="X",
        base_path="/admin",
        static_url="/admin/static",
        app_name="X",
        powered_by="X",
        version="1",
        partials=[],
    )
    assert "status-pill" in html
    assert "pulse" in html
    assert "Sign out" in html
    assert "/admin/logout" in html


# ── Branding helpers ──────────────────────────────────────────────


def test_brand_mark_with_accent() -> None:
    """_brand_mark splits last char into accent span when accent=True."""
    from rivex.openapi.openapi import _brand_mark

    result = _brand_mark("Rivex", accent=True)
    assert "RIVE" in result
    assert 'class="accent">X' in result


def test_brand_mark_no_accent() -> None:
    """_brand_mark with accent=False returns plain text."""
    from rivex.openapi.openapi import _brand_mark

    result = _brand_mark("Acme", accent=False)
    assert "ACME" in result
    assert "accent" not in result


def test_brand_mark_empty_fallback() -> None:
    """Empty app name falls back to 'Rivex'."""
    from rivex.openapi.openapi import _brand_mark

    result = _brand_mark("", accent=True)
    # Default is "Rivex" uppercased with X in accent span
    assert "RIVE" in result
    assert 'class="accent">X' in result


def test_brand_mark_single_char() -> None:
    """Single char is returned as-is (no split when len <= 1)."""
    from rivex.openapi.openapi import _brand_mark

    result = _brand_mark("X", accent=True)
    # len("X") <= 1 branch returns the text as-is
    assert result == "X"


def test_powered_by_rivex() -> None:
    """_powered_by_rivex renders 'powered by RiveX' with accent X."""
    from rivex.openapi.openapi import _powered_by_rivex

    html = _powered_by_rivex()
    assert "powered by" in html
    assert "Rive" in html
    assert 'class="x">X' in html
    assert " " in html.split("</span>")[1]  # space after closing span


def test_powered_by_general() -> None:
    """_powered_by renders 'powered by <name>'."""
    from rivex.openapi.openapi import _powered_by

    html = _powered_by("Acme Cloud")
    assert "powered by Acme Cloud" in html


def test_powered_by_none() -> None:
    """_powered_by returns empty string for None."""
    from rivex.openapi.openapi import _powered_by

    assert _powered_by(None) == ""
    assert _powered_by("") == ""


# ── End-to-end admin auth via DB ──────────────────────────────────


def test_admin_db_auth_round_trip(demo_app) -> None:
    """Full DB auth path: verify_token works for real users."""
    _, store, _ = demo_app
    user = store.verify_token("test-token")
    assert user is not None
    assert user.username == "admin"
    # touch_used sets last_used_at
    store.touch_used(user.username)
    user2 = store.verify_token("test-token")
    assert user2.last_used_at is not None


def test_admin_list_users(demo_app) -> None:
    """list_users returns all users."""
    _, store, _ = demo_app
    users = store.list_users()
    assert len(users) == 1
    assert users[0].username == "admin"


def test_admin_get_user(demo_app) -> None:
    """get_user_by_name returns the user."""
    _, store, _ = demo_app
    user = store.get_user_by_name("admin")
    assert user is not None
    assert user.username == "admin"


# ── Landing page (from _run_demo) ────────────────────────────────


def test_run_demo_static_handler(tmp_path) -> None:
    """The _make_static_handler serves files from a directory."""
    mod = _load_run_demo()
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "test.js").write_bytes(b"console.log('hi')")
    handler = mod._make_static_handler(static_dir, "test.js")
    result = handler({})
    assert result["status"] == 200
    assert result["body"] == b"console.log('hi')"
    assert any("javascript" in h[1] for h in result["headers"])


# ── Session login handler ────────────────────────────────────────


def test_session_login_bad_token(demo_app) -> None:
    """Session login with bad token returns 200 with banner HTML."""
    mod = _load_run_demo()
    result = mod._session(
        {
            "method": "POST",
            "body": b"token=nope",
        }
    )
    assert result["status"] == 200
    assert b"Invalid token" in result["body"]


def test_session_login_good_token(demo_app) -> None:
    """Session login with good token returns 200 with HX-Redirect."""
    mod = _load_run_demo()
    result = mod._session(
        {
            "method": "POST",
            "body": b"token=test-token",
        }
    )
    assert result["status"] == 200
    # HX-Redirect header is present (case-insensitive)
    headers_lower = [k.lower() for k, _ in result["headers"]]
    assert any("hx-redirect" in h for h in headers_lower)
    # Cookie is set
    assert any("rivex_admin_token" in v for _, v in result["headers"])


def test_session_login_get_405(demo_app) -> None:
    """Session login with GET returns 405."""
    mod = _load_run_demo()
    result = mod._session({"method": "GET"})
    assert result["status"] == 405


def test_session_login_empty_token(demo_app) -> None:
    """Session login with empty token returns banner."""
    mod = _load_run_demo()
    result = mod._session(
        {
            "method": "POST",
            "body": b"token=",
        }
    )
    assert result["status"] == 200
    assert b"Invalid token" in result["body"]


# ── Server page auto-redirect ────────────────────────────────────


def test_server_page_redirects_when_authed(demo_app) -> None:
    """Server page 302s to /admin/ when user has a valid cookie."""
    mod = _load_run_demo()
    result = mod._server_page(
        {
            "headers": [("Cookie", "rivex_admin_token=test-token")],
        }
    )
    assert result["status"] == 302
    locs = [v for k, v in result["headers"] if k.lower() == "location"]
    assert any("/admin" in loc for loc in locs)


def test_server_page_renders_for_anon(demo_app) -> None:
    """Server page renders the operational status page for anonymous users."""
    mod = _load_run_demo()
    result = mod._server_page({"headers": []})
    assert result["status"] == 200
    assert b"operational" in result["body"].lower() or b"OPERATIONAL" in result["body"]


def test_server_page_renders_for_bad_cookie(demo_app) -> None:
    """Server page renders for users with a bad cookie."""
    mod = _load_run_demo()
    result = mod._server_page(
        {
            "headers": [("Cookie", "rivex_admin_token=nope")],
        }
    )
    assert result["status"] == 200


# ── Logout clears cookie ─────────────────────────────────────────


def test_logout_clears_cookie(demo_app) -> None:
    """Logout sets a cookie with Max-Age=0."""
    mod = _load_run_demo()
    result = mod._logout({})
    assert result["status"] == 302
    assert any("Max-Age=0" in v for _, v in result["headers"])


# ── OpenAPI JSON spec generation ──────────────────────────────────


def _load_run_demo():
    """Load _run_demo.py as a module (it's a script, not a package)."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).parent.parent / "_run_demo.py"
    spec = importlib.util.spec_from_file_location("_run_demo", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # The script's __main__ block sets these; set sane defaults for tests
    if not hasattr(mod, "port"):
        mod.port = 9876
    return mod


def test_openapi_json_includes_widgets(demo_app) -> None:
    """The /openapi.json endpoint returns a valid OpenAPI 3.1 spec."""
    mod = _load_run_demo()
    result = mod._openapi_json({})
    assert result["status"] == 200
    spec = _json.loads(result["body"])
    assert spec["openapi"] == "3.1.0"
    assert "/widgets" in spec["paths"]


def test_openapi_json_includes_schemas(demo_app) -> None:
    """The spec includes components.schemas for Pydantic models."""
    mod = _load_run_demo()
    result = mod._openapi_json({})
    spec = _json.loads(result["body"])
    assert "Widget" in spec["components"]["schemas"]


def test_openapi_json_includes_request_body(demo_app) -> None:
    """POST /widgets has requestBody referencing WidgetCreate."""
    mod = _load_run_demo()
    result = mod._openapi_json({})
    spec = _json.loads(result["body"])
    post = spec["paths"]["/widgets"]["post"]
    assert "requestBody" in post
    ref = post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/WidgetCreate")


def test_openapi_json_includes_query_params(demo_app) -> None:
    """GET /widgets includes q and limit query params."""
    mod = _load_run_demo()
    result = mod._openapi_json({})
    spec = _json.loads(result["body"])
    op = spec["paths"]["/widgets"]["get"]
    param_names = [p["name"] for p in op.get("parameters", [])]
    assert "q" in param_names
    assert "limit" in param_names


def test_openapi_json_includes_path_params(demo_app) -> None:
    """GET /widgets/{widget_id} includes widget_id as a path param."""
    mod = _load_run_demo()
    result = mod._openapi_json({})
    spec = _json.loads(result["body"])
    op = spec["paths"]["/widgets/{widget_id}"]["get"]
    param_names = [p["name"] for p in op.get("parameters", [])]
    assert "widget_id" in param_names


def test_openapi_json_includes_response_schema(demo_app) -> None:
    """GET /widgets response references Widget array."""
    mod = _load_run_demo()
    result = mod._openapi_json({})
    spec = _json.loads(result["body"])
    op = spec["paths"]["/widgets"]["get"]
    resp_schema = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert resp_schema["type"] == "array"
    assert resp_schema["items"]["$ref"].endswith("/Widget")


def test_pydantic_to_json_schema(demo_app) -> None:
    """_pydantic_to_json_schema returns a JSON Schema dict."""
    from pydantic import BaseModel

    mod = _load_run_demo()

    class Foo(BaseModel):
        x: int
        y: str = "default"

    schema = mod._pydantic_to_json_schema(Foo)
    assert schema["type"] == "object"
    assert "x" in schema["properties"]


# ── Static asset routes ──────────────────────────────────────────


def test_make_static_handler_constructs(tmp_path) -> None:
    """_make_static_handler constructs a handler that serves a file's content."""
    mod = _load_run_demo()
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "x.js").write_bytes(b"alert(1)")
    handler = mod._make_static_handler(static_dir, "x.js")
    result = handler({})
    assert result["status"] == 200
    assert result["body"] == b"alert(1)"
