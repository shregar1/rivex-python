from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import rivex_core
from rivex.core._injection import build_handler_wrapper


class ASGIAdapter:
    """ASGI application adapter for Rivex.

    Wraps a Rivex app to speak the ASGI protocol, enabling deployment
    with uvicorn, hypercorn, daphne, or any ASGI server.

    Usage::

        from rivex import Rivex
        from rivex.asgi import ASGIAdapter

        app = Rivex()

        @app.get("/hello")
        def hello():
            return {"message": "world"}

        asgi_app = ASGIAdapter(app)
        # uvicorn my_module:asgi_app
    """

    def __init__(self, rivex_app: Any) -> None:
        self._app = rivex_app
        self._asgi_router = rivex_core.RivexASGI()
        self._handlers: list[Callable] = []
        self._ws_handlers: dict[str, Callable] = {}
        # Host-specific routes: host -> [(method, path, handler)]
        # Populated in _build() for routes with a host constraint.
        self._host_routes: dict[str, list[tuple[str, str, Callable]]] = {}
        # Const-route cache for the ASGI path. Mirrors the
        # ``RivexServer`` / ``RivexSyncServer`` const cache so the
        # same pre-baked responses are served when running under
        # uvicorn. Keyed by ``(method_uppercase, path)`` → tuple of
        # (status, headers, body).
        self._const_routes: dict[tuple[str, str], tuple[int, list[tuple[bytes, bytes]], bytes]] = {}
        self._built = False

    def _build(self) -> None:
        if self._built:
            return
        self._built = True

        # Populate the const-route cache from the Rust engine.
        # We can't go through the Rust struct fields directly
        # (they're private); instead we ask the engine for the
        # pre-baked routes it knows about and mirror them into the
        # ASGI dispatcher. The Rust side already validated the
        # inputs at registration time.
        for entry in self._app._server.get_const_routes():
            # Each entry is a 5-tuple: (method, path, status, body, headers)
            method, path, status, body, headers = entry
            raw_headers = []
            for h in headers:
                name, value = h
                if isinstance(name, str):
                    name = name.encode("latin-1")
                if isinstance(value, str):
                    value = value.encode("latin-1")
                raw_headers.append((name, value))
            self._const_routes[(method, path)] = (status, raw_headers, bytes(body))

        exc_handlers = self._app._exception_handlers or None
        dep_overrides = self._app.dependency_overrides or None

        for record in self._app._routes:
            jwt_config = getattr(record.endpoint, "_rivex_jwt_config", None)
            wrapper = build_handler_wrapper(
                record.endpoint,
                record.path,
                record.status_code,
                self._app.debug,
                exc_handlers,
                record.response_model,
                dep_overrides,
                response_model_include=record.response_model_include,
                response_model_exclude=record.response_model_exclude,
                response_model_exclude_unset=record.response_model_exclude_unset,
                response_model_exclude_defaults=record.response_model_exclude_defaults,
                response_model_exclude_none=record.response_model_exclude_none,
            )
            handler = self._apply_middleware(wrapper)
            if jwt_config:
                from rivex.auth.auth import _build_jwt_wrapper
                handler = _build_jwt_wrapper(handler, jwt_config)
            if record.host:
                self._host_routes.setdefault(record.host, []).append(
                    (record.method, record.path, handler)
                )
                continue
            self._handlers.append(handler)
            try:
                self._asgi_router.add_route(record.method, record.path, handler)
            except ValueError:
                # Surface duplicate route registration as a
                # warning instead of silently swallowing it. The
                # previous silent-pass hid bugs where a route
                # appeared registered but actually wasn't.
                import warnings

                warnings.warn(
                    f"Duplicate ASGI route: {record.method} {record.path}",
                    stacklevel=2,
                )

        for ws_path, ws_handler in self._app._ws_routes:
            self._ws_handlers[ws_path] = ws_handler

        _mount_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
        for mount_path, mount_app in self._app._mounts:
            prefix = mount_path.rstrip("/")

            async def _mount_handler(
                request_data: dict,
                *,
                _app: Any = mount_app,
                _prefix: str = prefix,
            ) -> dict:
                original = request_data.get("path", "/")
                request_data = dict(request_data)
                request_data["path"] = original[len(_prefix):] or "/"
                result: dict = await _app(request_data)
                return result

            catch_all = prefix + "/{path:path}"
            for method in _mount_methods:
                try:
                    self._asgi_router.add_route(method, catch_all, _mount_handler)
                except ValueError:
                    pass

            # Also register the exact mount path (no trailing slash)
            try:
                self._asgi_router.add_route("GET", mount_path, _mount_handler)
            except ValueError:
                pass

    def _apply_middleware(self, handler: Callable) -> Callable:
        from rivex.middleware._mw_utils import apply_middleware_chain

        return apply_middleware_chain(handler, self._app._middleware)

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        self._build()

        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
        elif scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)

    async def _handle_http(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        method = scope["method"]
        path = scope["path"]
        query_string = scope.get("query_string", b"")
        if isinstance(query_string, bytes):
            query_string = query_string.decode("latin-1")

        headers_raw = scope.get("headers", [])
        header_list = []
        for name, value in headers_raw:
            if isinstance(name, bytes):
                name = name.decode("latin-1")
            if isinstance(value, bytes):
                value = value.decode("latin-1")
            header_list.append((name, value))

        client = scope.get("client")
        client_host = client[0] if client else None
        client_port = client[1] if client else None

        # Const-route fast path — same idea as Robyn's
        # ``default_service`` short-circuit and as the Rust
        # ``listener.rs`` const cache. Pre-baked responses are
        # served verbatim, with no Python handler call, no matchit
        # walk, and no dependency injection.
        const = self._const_routes.get((method, path))
        if const is not None:
            status, headers, body = const
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": headers,
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        # Host-specific route resolution. Check if there are routes
        # registered with a host constraint matching the request's
        # Host header. If so, do a linear scan for matching method
        # and path, then fall back to the general router.
        host_header = None
        for name, value in header_list:
            if name.lower() == "host":
                host_header = value
                break

        host_routes = self._host_routes.get(host_header) if host_header else None
        if host_routes is not None:
            for route_method, route_path, handler in host_routes:
                if route_method != method:
                    continue
                resolved = rivex_core.match_path(route_path, path)
                if resolved is not None:
                    await self._dispatch_handler(
                        handler, method, path,
                        query_string, body, header_list, resolved,
                        client_host, client_port, send,
                    )
                    return

        result = self._asgi_router.resolve(method, path)

        if result is None:
            methods = self._asgi_router.methods_for_path(path)
            if methods:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 405,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b'{"detail":"Method Not Allowed"}',
                    }
                )
            else:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b'{"detail":"Not Found"}',
                    }
                )
            return

        handler, path_params = result
        await self._dispatch_handler(
            handler, method, path,
            query_string, body, header_list, dict(path_params),
            client_host, client_port, send,
        )

    async def _dispatch_handler(
        self,
        handler: Callable,
        method: str,
        path: str,
        query_string: str,
        body: bytes,
        header_list: list[tuple[str, str]],
        path_params: dict[str, str],
        client_host: str | None,
        client_port: int | None,
        send: Callable,
    ) -> None:
        request_data = {
            "method": method,
            "path": path,
            "query_string": query_string,
            "body": body,
            "headers": header_list,
            "path_params": dict(path_params),
        }
        if client_host:
            request_data["client_host"] = client_host
        if client_port:
            request_data["client_port"] = client_port

        if asyncio.iscoroutinefunction(handler):
            response = await handler(request_data)
        else:
            response = handler(request_data)
            if asyncio.iscoroutine(response):
                response = await response

        status = response.get("status", 200)
        resp_headers = []
        for name, value in response.get("headers", []):
            if isinstance(name, str):
                name = name.encode("latin-1")
            if isinstance(value, str):
                value = value.encode("latin-1")
            resp_headers.append((name, value))

        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": resp_headers,
            }
        )

        stream_iter = response.get("_stream_iter")
        if stream_iter is not None:
            is_async = response.get("_stream_async", True)
            if is_async:
                async for chunk in stream_iter:
                    if isinstance(chunk, str):
                        chunk = chunk.encode("utf-8")
                    await send(
                        {
                            "type": "http.response.body",
                            "body": chunk,
                            "more_body": True,
                        }
                    )
            else:
                for chunk in stream_iter:
                    if isinstance(chunk, str):
                        chunk = chunk.encode("utf-8")
                    await send(
                        {
                            "type": "http.response.body",
                            "body": chunk,
                            "more_body": True,
                        }
                    )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                    "more_body": False,
                }
            )
        else:
            if "body_json" in response:
                import json as _json

                resp_body = _json.dumps(response["body_json"]).encode("utf-8")
            else:
                resp_body = response.get("body", b"")
            if isinstance(resp_body, str):
                resp_body = resp_body.encode("utf-8")
            await send(
                {
                    "type": "http.response.body",
                    "body": resp_body,
                }
            )

    async def _handle_websocket(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        path = scope["path"]
        handler = self._ws_handlers.get(path)
        if handler is None:
            await send({"type": "websocket.close", "code": 4004})
            return

        ws = ASGIWebSocket(scope, receive, send)
        try:
            await handler(ws)
        except Exception:
            try:
                await ws.close(1011, "Internal error")
            except Exception:
                pass

    async def _handle_lifespan(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        state = None
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    state = self._app._enter_lifespan()
                    self._app._run_hooks(self._app._startup_hooks)
                except Exception:
                    # Per ASGI 3.0 spec, a failed startup MUST be reported
                    # via `lifespan.startup.failed` so servers (uvicorn,
                    # hypercorn, daphne) can surface the error and shut
                    # down cleanly instead of hanging.
                    await send({"type": "lifespan.startup.failed", "message": "startup failed"})
                    return
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                try:
                    self._app._run_hooks(self._app._shutdown_hooks)
                    self._app._exit_lifespan(state)
                except Exception:
                    await send({"type": "lifespan.shutdown.failed", "message": "shutdown failed"})
                    return
                await send({"type": "lifespan.shutdown.complete"})
                return


class ASGIWebSocket:
    """WebSocket wrapper for the ASGI protocol."""

    def __init__(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        self.scope = scope
        self._receive = receive
        self._send = send
        self._accepted = False
        self.path = scope.get("path", "/")
        self.query_string = (
            scope.get("query_string", b"").decode("latin-1")
            if isinstance(scope.get("query_string", b""), bytes)
            else scope.get("query_string", "")
        )
        self.path_params: dict[str, str] = scope.get("path_params", {})
        headers_raw = scope.get("headers", [])
        self.headers: dict[str, str] = {}
        for name, value in headers_raw:
            if isinstance(name, bytes):
                name = name.decode("latin-1")
            if isinstance(value, bytes):
                value = value.decode("latin-1")
            self.headers[name.lower()] = value

    async def accept(self, subprotocol: str | None = None) -> None:
        msg: dict[str, Any] = {"type": "websocket.accept"}
        if subprotocol:
            msg["subprotocol"] = subprotocol
        await self._send(msg)
        self._accepted = True

    async def _ensure_accepted(self) -> None:
        """Auto-accept on the first read.

        FastAPI and Starlette both accept the connection lazily on the
        first ``receive_*`` call if the user hasn't called
        ``accept()`` explicitly. We do the same so handlers written
        like ``await ws.receive_text()`` work without the user having
        to remember to call ``accept()`` first.
        """
        if self._accepted:
            return
        await self.accept()

    async def receive_text(self) -> str:
        await self._ensure_accepted()
        while True:
            message = await self._receive()
            if message["type"] == "websocket.disconnect":
                from rivex.core.exceptions import WebSocketDisconnect

                raise WebSocketDisconnect(code=message.get("code", 1000))
            if message["type"] in ("websocket.connect", "websocket.accept"):
                # First message is the connection handshake; skip it.
                continue
            text: str = message.get("text", "")
            return text

    async def receive_bytes(self) -> bytes:
        await self._ensure_accepted()
        while True:
            message = await self._receive()
            if message["type"] == "websocket.disconnect":
                from rivex.core.exceptions import WebSocketDisconnect

                raise WebSocketDisconnect(code=message.get("code", 1000))
            if message["type"] in ("websocket.connect", "websocket.accept"):
                continue
            data: bytes = message.get("bytes", b"")
            return data

    async def receive_json(self, mode: str = "text") -> Any:
        import json

        if mode == "text":
            text = await self.receive_text()
            return json.loads(text)
        data = await self.receive_bytes()
        return json.loads(data)

    async def send_text(self, data: str) -> None:
        await self._send({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        await self._send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any, mode: str = "text") -> None:
        import json

        text = json.dumps(data)
        if mode == "text":
            await self.send_text(text)
        else:
            await self.send_bytes(text.encode("utf-8"))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        await self._send({"type": "websocket.close", "code": code, "reason": reason})
