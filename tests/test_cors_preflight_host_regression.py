"""Regression test for the CORS-preflight ``host`` shadowing bug (0.2.2).

In 0.2.2, ``Rivex._drive_rust_server`` reused the name ``host`` for the
per-route host constraint inside the CORS-preflight registration loop
(``host = path_hosts.get(path)``), clobbering the method's server
bind-address parameter. When the last path iterated had no host
constraint — the common case — the final ``server.run(host, port)``
received ``None`` and the Rust engine raised ``TypeError: argument
'host': 'NoneType' object cannot be converted to 'PyString'``. Every
CORS-enabled app with at least one hostless route crashed at boot.

The loop local is now called ``route_host``; these tests pin the fix by
driving ``_drive_rust_server`` against a fake engine and asserting the
bind address survives to ``server.run``.
"""

from __future__ import annotations

from typing import Any, Callable

from rivex import Rivex
from rivex.middleware.middleware import CORSMiddleware


class _FakeServer:
    """Minimal stand-in for the Rust engine's registration surface."""

    def __init__(self) -> None:
        self.routes: list[tuple[str, str, str | None]] = []
        self.run_args: tuple[Any, Any] | None = None

    def add_route(
        self,
        method: str,
        path: str,
        handler: Callable,
        host: str | None = None,
    ) -> None:
        self.routes.append((method, path, host))

    def add_const_route(self, *args: Any, **kwargs: Any) -> None:
        pass

    def add_websocket_route(self, *args: Any, **kwargs: Any) -> None:
        pass

    def set_security(self, *args: Any, **kwargs: Any) -> None:
        pass

    def run(self, host: Any, port: Any) -> None:
        self.run_args = (host, port)


def _boot(app: Rivex) -> _FakeServer:
    server = _FakeServer()
    app._drive_rust_server(server, "127.0.0.1", 8123, supports_ws=False)
    return server


def test_cors_app_with_hostless_route_keeps_bind_host() -> None:
    """The 0.2.2 crash: a hostless route made ``server.run`` receive None."""
    app = Rivex()
    app.add_middleware(CORSMiddleware, allow_origins=["*"])

    @app.get("/things")
    async def things() -> dict:
        return {"ok": True}

    server = _boot(app)

    assert server.run_args == ("127.0.0.1", 8123)


def test_cors_preflight_registered_with_route_host_constraint() -> None:
    """Preflights keep per-route host filters without touching the bind host."""
    app = Rivex()
    app.add_middleware(CORSMiddleware, allow_origins=["*"])

    @app.get("/open")
    async def open_route() -> dict:
        return {"ok": True}

    @app.get("/scoped", host="api.example.com")
    async def scoped_route() -> dict:
        return {"ok": True}

    server = _boot(app)

    preflights = {
        (path, host) for method, path, host in server.routes if method == "OPTIONS"
    }
    assert ("/open", None) in preflights
    assert ("/scoped", "api.example.com") in preflights
    # Regardless of preflight registration order, the bind address must
    # reach the engine unchanged.
    assert server.run_args == ("127.0.0.1", 8123)
