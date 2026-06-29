"""Tests for ``app.mount()`` — sub-application mounting."""

from __future__ import annotations

import pytest

from rivex import Rivex
from rivex.testing import TestClient


def test_mount_sub_app_routes():
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


def test_mount_sub_app_with_post():
    admin = Rivex()

    @admin.post("/items")
    async def create_item():
        return {"created": True}

    app = Rivex()
    app.mount("/api", admin)

    client = TestClient(app)
    resp = client.post("/api/items")
    assert resp.status_code == 200
    assert resp.json()["created"] is True


def test_mount_sub_app_with_path_params():
    admin = Rivex()

    @admin.get("/items/{item_id}")
    async def get_item(item_id: int):
        return {"item_id": item_id}

    app = Rivex()
    app.mount("/admin", admin)

    client = TestClient(app)
    resp = client.get("/admin/items/42")
    assert resp.status_code == 200
    assert resp.json()["item_id"] == 42


def test_mount_multiple_sub_apps():
    admin = Rivex()

    @admin.get("/dashboard")
    async def dashboard():
        return {"page": "dashboard"}

    api = Rivex()

    @api.get("/version")
    async def version():
        return {"version": "1.0"}

    app = Rivex()
    app.mount("/admin", admin)
    app.mount("/api", api)

    client = TestClient(app)
    resp1 = client.get("/admin/dashboard")
    assert resp1.status_code == 200
    assert resp1.json()["page"] == "dashboard"

    resp2 = client.get("/api/version")
    assert resp2.status_code == 200
    assert resp2.json()["version"] == "1.0"


def test_mount_generic_asgi_callable():
    """Mount a plain dict-to-dict callable (like StaticFiles)."""

    async def static_handler(request_data: dict) -> dict:
        path = request_data.get("path", "/")
        return {
            "status": 200,
            "headers": [("content-type", "text/plain")],
            "body": f"static {path}".encode(),
        }

    app = Rivex()
    app.mount("/static", static_handler)

    client = TestClient(app)
    resp = client.get("/static/file.txt")
    assert resp.status_code == 200
    assert resp.text == "static /file.txt"


def test_mount_generic_asgi_callable_post():
    async def handler(request_data: dict) -> dict:
        return {
            "status": 201,
            "headers": [("content-type", "application/json")],
            "body": b'{"ok": true}',
        }

    app = Rivex()
    app.mount("/api", handler)

    client = TestClient(app)
    resp = client.post("/api/resource")
    assert resp.status_code == 201


def test_mount_root_path():
    """Mount on root path should work with sub-app's routes."""

    sub = Rivex()

    @sub.get("/hello")
    async def hello():
        return {"msg": "world"}

    app = Rivex()
    app.mount("/", sub)

    client = TestClient(app)
    resp = client.get("/hello")
    assert resp.status_code == 200
    assert resp.json()["msg"] == "world"


def test_mount_404_for_unknown_sub_path():
    admin = Rivex()

    @admin.get("/users")
    async def users():
        return []

    app = Rivex()
    app.mount("/admin", admin)

    client = TestClient(app)
    resp = client.get("/admin/nonexistent")
    assert resp.status_code == 404


def test_mount_nested_sub_apps():
    """Sub-app mounted inside another sub-app."""
    inner = Rivex()

    @inner.get("/data")
    async def data():
        return {"value": 1}

    middle = Rivex()
    middle.mount("/inner", inner)

    app = Rivex()
    app.mount("/outer", middle)

    client = TestClient(app)
    resp = client.get("/outer/inner/data")
    assert resp.status_code == 200
    assert resp.json()["value"] == 1
