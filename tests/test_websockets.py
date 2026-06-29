"""End-to-end WebSocket tests.

Spins up a real Rivex server on a localhost port, connects with the
``websockets`` client, and exercises text echo, JSON round-trip, and
concurrent connections.

Marked async so they run on the same event loop the client uses.
"""

from __future__ import annotations

import asyncio
import json as _stdlib_json
import socket
import threading
import time

import pytest

# ``websockets`` is the de-facto Python WS client — we use it as the
# adversarial side of these tests. Imported via ``importorskip`` so the
# suite still passes on machines without it.
websockets = pytest.importorskip("websockets")

from rivex import Rivex, WebSocket  # noqa: E402 — order matters: must follow importorskip


def _free_port() -> int:
    """Grab an ephemeral port the kernel won't reassign immediately."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_server(app: Rivex) -> int:
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


def _ws_app() -> Rivex:
    app = Rivex()

    @app.websocket("/echo")
    async def echo(ws: WebSocket) -> None:
        while True:
            msg = await ws.receive_text()
            if msg is None:
                return
            await ws.send_text(f"echo: {msg}")
            if msg == "quit":
                return

    @app.websocket("/json")
    async def json_route(ws: WebSocket) -> None:
        payload = await ws.receive_json()
        if payload is None:
            return
        await ws.send_json({"got": payload, "sum": sum(payload.get("xs", []))})

    @app.websocket("/binary")
    async def binary_route(ws: WebSocket) -> None:
        data = await ws.receive_bytes()
        if data is None:
            return
        await ws.send_bytes(data[::-1])  # echo reversed

    return app


@pytest.fixture(scope="module")
def server() -> tuple[str, int]:
    port = _free_port()
    port = _start_server(_ws_app())
    return ("127.0.0.1", port)


@pytest.mark.asyncio
async def test_text_echo(server: tuple[str, int]) -> None:
    host, port = server
    async with websockets.connect(f"ws://{host}:{port}/echo") as ws:
        await ws.send("hello")
        assert await ws.recv() == "echo: hello"
        await ws.send("world")
        assert await ws.recv() == "echo: world"
        await ws.send("quit")
        assert await ws.recv() == "echo: quit"


@pytest.mark.asyncio
async def test_json_round_trip(server: tuple[str, int]) -> None:
    host, port = server
    async with websockets.connect(f"ws://{host}:{port}/json") as ws:
        await ws.send(_stdlib_json.dumps({"xs": [1, 2, 3, 4]}))
        reply = _stdlib_json.loads(await ws.recv())
        assert reply == {"got": {"xs": [1, 2, 3, 4]}, "sum": 10}


@pytest.mark.asyncio
async def test_binary_round_trip(server: tuple[str, int]) -> None:
    host, port = server
    async with websockets.connect(f"ws://{host}:{port}/binary") as ws:
        await ws.send(b"\x01\x02\x03\x04")
        reply = await ws.recv()
        assert reply == b"\x04\x03\x02\x01"


@pytest.mark.asyncio
async def test_many_concurrent_connections(server: tuple[str, int]) -> None:
    """Five parallel echo connections — each gets its own handler thread
    + asyncio event loop on the server, so they shouldn't serialise."""
    host, port = server

    async def one_session(i: int) -> None:
        async with websockets.connect(f"ws://{host}:{port}/echo") as ws:
            await ws.send(f"hi {i}")
            assert await ws.recv() == f"echo: hi {i}"

    await asyncio.gather(*[one_session(i) for i in range(5)])


@pytest.mark.asyncio
async def test_unmatched_path_returns_normal_http_404(server: tuple[str, int]) -> None:
    """A request with WS upgrade headers on a path with no registered
    handler should fall through to the normal HTTP path and 404."""
    host, port = server
    # The websockets library split its exceptions between
    # ``websockets.exceptions`` (the new public API) and
    # ``websockets.legacy.exceptions`` (the older one the
    # ``websockets.ClientConnection`` still uses). Catch the base
    # class so we work against either.
    exc_types = (
        getattr(getattr(websockets, "exceptions", None), "InvalidStatus", Exception),
        getattr(
            getattr(websockets, "legacy", None), "exceptions", None
        )
        and getattr(websockets.legacy.exceptions, "InvalidStatusCode", Exception),
    )
    exc_types = tuple(t for t in exc_types if isinstance(t, type) and issubclass(t, Exception))
    with pytest.raises(exc_types) as ei:
        async with websockets.connect(f"ws://{host}:{port}/no-such-route") as _ws:
            pass
    # ``ei.value`` exposes the status code via either ``.response.status_code``
    # (the new public API in ``websockets.exceptions``) or as a direct
    # ``.status_code`` attribute (the legacy exception used internally by
    # the client when the handshake rejects the upgrade).  Pick whichever
    # the raised exception provides.
    exc = ei.value
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        if response is not None:
            status = getattr(response, "status_code", None)
    assert status is not None, f"no status code on {type(exc).__name__}"
    assert 400 <= status < 500, f"expected 4xx, got {status}"
