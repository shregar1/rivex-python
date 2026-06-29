"""Tier 3 — SSE (Server-Sent Events) tests.

Coverage:

- SseEvent dataclass formats correctly
- @app.sse() decorator registers and serves streaming events
- Multiple events can be streamed
- EventSourceResponse works end-to-end
"""
import json
import socket
import threading
import time
from typing import Any

import pytest

import rivex
from rivex.responses import EventSourceResponse
from rivex.sse import SseEvent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(app: rivex.Rivex) -> int:
    """Start the engine on a free port in a daemon thread, retrying on a
    fresh port if the bind races (``_free_port`` closes its probe socket
    before the server binds, so the OS can hand the same port to two
    servers). Returns the live port once it is accepting connections."""
    last_port = None
    for _ in range(12):
        port = _free_port()
        last_port = port

        def _run(p=port) -> None:
            try:
                app.run(host="127.0.0.1", port=p)
            except Exception:
                pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if not t.is_alive():
                break  # thread exited — almost always a bind collision
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    return port
            except OSError:
                time.sleep(0.05)
    raise RuntimeError(f"server did not start (last tried port {last_port})")


# ── SseEvent formatting ────────────────────────────────────────────


class TestSseEvent:
    def test_data_only(self) -> None:
        ev = SseEvent(data="hello")
        result = ev._format()
        assert "data: hello" in result
        assert result.endswith("\n\n")

    def test_data_and_event(self) -> None:
        ev = SseEvent(data="update", event="status")
        result = ev._format()
        assert "event: status" in result
        assert "data: update" in result

    def test_with_id_and_retry(self) -> None:
        ev = SseEvent(data="msg", id="42", retry=3000)
        result = ev._format()
        assert "id: 42" in result
        assert "retry: 3000" in result
        assert "data: msg" in result

    def test_json_encoding(self) -> None:
        ev = SseEvent(data={"key": "value"}, json=True)
        result = ev._format()
        assert "data: " in result
        assert '"key"' in result
        assert '"value"' in result

    def test_multiline_data(self) -> None:
        ev = SseEvent(data="line1\nline2")
        result = ev._format()
        assert "data: line1" in result
        assert "data: line2" in result


# ── EventSourceResponse formatting ─────────────────────────────────


class TestEventSourceResponse:
    def test_format_event_static(self) -> None:
        s = EventSourceResponse.format_event(data="hello")
        assert "data: hello" in s
        assert s.endswith("\n\n")

    def test_format_event_with_event_type(self) -> None:
        s = EventSourceResponse.format_event(data="x", event="update")
        assert "event: update" in s


# ── End-to-end SSE server tests ────────────────────────────────────


def _http_get(url: str, timeout: float = 5) -> tuple[int, dict, bytes]:
    import urllib.error as _ue
    import urllib.request as _ur
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = _ur.Request(url)
            with _ur.urlopen(req, timeout=min(3.0, timeout)) as resp:
                return resp.status, dict(resp.getheaders()), resp.read()
        except _ue.HTTPError as e:
            return e.code, dict(e.headers or {}), e.read()
        except ConnectionResetError:
            time.sleep(0.05)
    raise RuntimeError(f"could not fetch {url}")


def test_sse_streams_single_event() -> None:
    app = rivex.Rivex()

    @app.sse("/events")
    async def events():
        yield SseEvent(data="hello")

    port = _free_port()
    port = _start_server(app)
    s, _, b = _http_get(f"http://127.0.0.1:{port}/events")
    assert s == 200
    assert b"data: hello" in b


def test_sse_streams_multiple_events() -> None:
    app = rivex.Rivex()

    @app.sse("/multi")
    async def multi():
        yield SseEvent(data="first")
        yield SseEvent(data="second", event="update", id="1")

    port = _free_port()
    port = _start_server(app)
    s, headers, b = _http_get(f"http://127.0.0.1:{port}/multi")
    assert s == 200
    ct = headers.get("content-type", "").lower()
    assert "text/event-stream" in ct
    assert b"data: first" in b
    assert b"event: update" in b
    assert b"id: 1" in b


def test_sse_returns_correct_headers() -> None:
    app = rivex.Rivex()

    @app.sse("/h")
    async def h():
        yield SseEvent(data="ok")

    port = _free_port()
    port = _start_server(app)
    s, headers, _ = _http_get(f"http://127.0.0.1:{port}/h")
    assert s == 200
    ct = headers.get("content-type", "").lower()
    assert "text/event-stream" in ct


def test_sse_works_alongside_normal_routes() -> None:
    app = rivex.Rivex()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.sse("/events")
    async def events():
        yield SseEvent(data="ping")

    port = _free_port()
    port = _start_server(app)
    s1, _, b1 = _http_get(f"http://127.0.0.1:{port}/health")
    assert s1 == 200
    s2, _, b2 = _http_get(f"http://127.0.0.1:{port}/events")
    assert s2 == 200
    assert b"data: ping" in b2


# ── Additional coverage: path params, streaming chunks ──────────────


def test_sse_with_path_param() -> None:
    app = rivex.Rivex()

    @app.sse("/stream/{topic}")
    async def stream(topic: str):
        yield SseEvent(data=f"subscribed to {topic}")

    port = _free_port()
    port = _start_server(app)
    s, _, b = _http_get(f"http://127.0.0.1:{port}/stream/news")
    assert s == 200
    assert b"subscribed to news" in b


def test_sse_path_param_not_found() -> None:
    app = rivex.Rivex()

    @app.sse("/stream/{topic}")
    async def stream(topic: str):
        yield SseEvent(data=topic)

    port = _free_port()
    port = _start_server(app)
    import urllib.error as _ue
    try:
        from urllib.request import urlopen
        urlopen(f"http://127.0.0.1:{port}/stream", timeout=2)
    except _ue.HTTPError as e:
        assert e.code in (404,)


def test_sse_long_stream() -> None:
    """Stream 100 events and verify all are received."""
    app = rivex.Rivex()

    @app.sse("/long")
    async def long():
        for i in range(100):
            yield SseEvent(data=str(i), id=str(i))

    port = _free_port()
    port = _start_server(app)
    _, _, body = _http_get(f"http://127.0.0.1:{port}/long", timeout=10)
    lines = body.decode().strip().split("\n")
    data_lines = [l for l in lines if l.startswith("data: ")]
    assert len(data_lines) == 100
    assert b"data: 0" in body
    assert b"data: 99" in body


def test_sse_custom_response_headers() -> None:
    """Use EventSourceResponse directly to set custom headers."""
    app = rivex.Rivex()

    @app.get("/custom-sse")
    async def custom_sse():
        content = iter([SseEvent(data="hello")._format()])
        resp = EventSourceResponse(content=content, headers={"X-Custom": "yes"})
        return resp

    port = _free_port()
    port = _start_server(app)
    s, headers, b = _http_get(f"http://127.0.0.1:{port}/custom-sse")
    assert s == 200
    assert headers.get("x-custom", "").lower() == "yes"
