"""Tests for AsyncAPI spec generation and endpoint."""

from __future__ import annotations

from rivex import Rivex
from rivex.openapi.asyncapi import build_asyncapi_html, generate_asyncapi
from rivex.testing.testing import TestClient


def test_generate_asyncapi_no_routes():
    spec = generate_asyncapi(ws_routes=[])
    assert spec["asyncapi"] == "2.6.0"
    assert spec["channels"] == {}


def test_generate_asyncapi_with_routes():
    async def chat_handler(ws):
        ...

    spec = generate_asyncapi(
        title="Chat API",
        version="1.0.0",
        ws_routes=[("/ws/chat", chat_handler)],
    )
    assert "ws.chat" in spec["channels"]
    assert spec["info"]["title"] == "Chat API"


def test_generate_asyncapi_with_docstring():
    async def chat_handler(ws):
        """Real-time chat over WebSocket."""
        ...

    spec = generate_asyncapi(ws_routes=[("/ws/chat", chat_handler)])
    channel = spec["channels"]["ws.chat"]
    assert channel["description"] == "Real-time chat over WebSocket."


def test_asyncapi_endpoint_returns_spec():
    app = Rivex(asyncapi_url="/asyncapi.json")

    @app.websocket("/ws/echo")
    async def echo(ws):
        ...

    client = TestClient(app)
    resp = client.get("/asyncapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asyncapi"] == "2.6.0"
    assert "ws.echo" in data["channels"]


def test_asyncapi_docs_page():
    app = Rivex(asyncapi_url="/asyncapi.json", asyncapi_docs_url="/asyncapi")

    @app.websocket("/ws/test")
    async def test_handler(ws):
        """Test handler."""
        ...

    client = TestClient(app)
    resp = client.get("/asyncapi")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert b"asyncapi-component" in resp.content


def test_no_asyncapi_when_no_ws_routes():
    app = Rivex(asyncapi_url="/asyncapi.json")

    client = TestClient(app)
    resp = client.get("/asyncapi.json")
    assert resp.status_code == 404


def test_asyncapi_via_constructor():
    """AsyncAPI endpoint is available when app is constructed with defaults."""
    app = Rivex()

    @app.websocket("/ws/chat")
    async def chat(ws):
        """Chat room WebSocket."""
        ...

    client = TestClient(app)
    resp = client.get("/asyncapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "Rivex"
