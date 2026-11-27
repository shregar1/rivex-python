from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import rivex_core
from rivex.di._injection import build_handler_wrapper


class ASGIAdapter:
    """ASGI application adapter for Rivex.

    Wraps a Rivex app to speak the ASGI protocol, enabling deployment
    with uvicorn, hypercorn, daphne, or any ASGI server.

    Usage::

        from rivex import Rivex
        from rivex.native.asgi import ASGIAdapter

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
        """Populate the ASGI dispatch tables from the wrapped Rivex app.

        Idempotent: subsequent invocations are a no-op thanks to the
        ``_built`` guard. On the first call, mirrors the pre-baked
        "const" routes from the Rust engine into ``_const_routes`` so they
        can be served without going through the Python router, wraps each
        regular route's endpoint with the dependency-injection and
        middleware stack, and registers the resulting handler in the
        underlying ``RivexASGI`` router. Mounted sub-apps are also wired
        in as catch-all handlers under their mount prefix. Duplicate
        registrations are surfaced via :mod:`warnings` so they are not
        silently swallowed.
        """
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
                """Strip the mount prefix and forward the request into the sub-app.

                Closes over the configured mount ``_prefix`` and the
                mounted ``_app`` so the underlying router sees the
                request as if it were aimed at the sub-app's root, with
                the path component truncated to its post-prefix form.
                """
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
        """Wrap ``handler`` with the app's middleware chain.

        Delegates to :func:`apply_middleware_chain` using the middleware
        list configured on the wrapped Rivex app, returning a callable
        that runs the chain around ``handler`` on every request.

        Args:
            handler: The route handler (already wrapped with
                dependency-injection) to be wrapped with middleware.

        Returns:
            A new callable that runs the configured middleware chain
            around ``handler``.
        """
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
        """Serve a single ASGI ``http`` request.

        Drains the request body from ``receive``, decodes the query
        string and headers out of the scope, and resolves the route in
        this order: the pre-baked const-route cache, host-scoped routes
        (registered with a ``host=`` constraint), then the global router.
        Matched requests are dispatched to their handler; unmatched
        requests yield ``404 Not Found`` and method-mismatched requests
        yield ``405 Method Not Allowed`` with a JSON body.

        Args:
            scope: ASGI ``http`` scope carrying the request metadata.
            receive: ASGI ``receive`` callable used to drain the request
                body.
            send: ASGI ``send`` callable used to emit the response.
        """
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
        """Build a request envelope and write the handler's response back to ASGI.

        Constructs the ``request_data`` dict consumed by Rivex handlers
        (method, path, query string, body, headers, and any extracted
        path parameters), invokes the handler — supporting both coroutine
        and synchronous callables — and serialises the resulting dict
        back to the ASGI caller. The handler may return either a regular
        ``{status, headers, body}`` dict or a streaming response
        (``_stream_iter`` / ``_stream_async``) which is forwarded chunk
        by chunk using ``more_body=True`` until the stream is exhausted.

        Args:
            handler: The resolved route handler, already wrapped with
                DI and middleware.
            method: HTTP method of the incoming request.
            path: URL path of the incoming request.
            query_string: Decoded query string (without leading ``?``).
            body: Raw request body bytes.
            header_list: Headers as decoded ``(name, value)`` string pairs.
            path_params: Path parameters extracted by the router, keyed
                by their name in the route template.
            client_host: Client host from the ASGI scope, or ``None``.
            client_port: Client port from the ASGI scope, or ``None``.
            send: ASGI ``send`` callable used to emit the response.
        """
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
        """Serve a single ASGI ``websocket`` connection.

        Looks up the path against the registered WebSocket handlers and
        dispatches the connection by handing the handler an
        :class:`ASGIWebSocket` wrapper. Unregistered paths are closed
        with code ``4004``; an exception raised by the user handler
        triggers a best-effort close with code ``1011`` and reason
        ``Internal error``.

        Args:
            scope: ASGI ``websocket`` scope carrying the request metadata.
            receive: ASGI ``receive`` callable for incoming frames.
            send: ASGI ``send`` callable for outgoing frames.
        """
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
        """Drive the ASGI ``lifespan`` event loop for the wrapped app.

        Translates ``lifespan.startup`` and ``lifespan.shutdown`` events
        from the server into the app's lifespan enter/exit calls and
        registered startup/shutdown hooks. On failure, reports
        ``lifespan.startup.failed`` or ``lifespan.shutdown.failed`` to
        the server so it can surface the error and shut down cleanly
        instead of hanging (per the ASGI 3.0 spec).

        Args:
            scope: ASGI ``lifespan`` scope.
            receive: ASGI ``receive`` callable for lifespan events.
            send: ASGI ``send`` callable used to acknowledge events.
        """
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
        """Send the ASGI ``websocket.accept`` message to the server.

        Args:
            subprotocol: Optional sub-protocol name negotiated with
                the client (e.g. ``"graphql-ws"``). When provided it is
                echoed back to the client in the accept frame.
        """
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
        """Read the next text frame from the client.

        Auto-accepts the connection on the first call if the handler
        has not done so explicitly. Skips the initial handshake messages
        (``websocket.connect`` / ``websocket.accept``) and returns the
        text payload of the next real frame.

        Returns:
            The UTF-8 text payload of the next message.

        Raises:
            WebSocketDisconnect: When the client closes the connection
                before a frame is received.
        """
        await self._ensure_accepted()
        while True:
            message = await self._receive()
            if message["type"] == "websocket.disconnect":
                from rivex.exceptions.http.exceptions import WebSocketDisconnect

                raise WebSocketDisconnect(code=message.get("code", 1000))
            if message["type"] in ("websocket.connect", "websocket.accept"):
                # First message is the connection handshake; skip it.
                continue
            text: str = message.get("text", "")
            return text

    async def receive_bytes(self) -> bytes:
        """Read the next binary frame from the client.

        Auto-accepts the connection on the first call if the handler
        has not done so explicitly. Skips the initial handshake messages
        and returns the binary payload of the next real frame.

        Returns:
            The raw bytes of the next message.

        Raises:
            WebSocketDisconnect: When the client closes the connection
                before a frame is received.
        """
        await self._ensure_accepted()
        while True:
            message = await self._receive()
            if message["type"] == "websocket.disconnect":
                from rivex.exceptions.http.exceptions import WebSocketDisconnect

                raise WebSocketDisconnect(code=message.get("code", 1000))
            if message["type"] in ("websocket.connect", "websocket.accept"):
                continue
            data: bytes = message.get("bytes", b"")
            return data

    async def receive_json(self, mode: str = "text") -> Any:
        """Read the next frame and parse it as JSON.

        Args:
            mode: ``"text"`` (default) reads a text frame and decodes
                the JSON from the UTF-8 payload. ``"binary"`` reads a
                binary frame and decodes the JSON from the bytes.

        Returns:
            The decoded JSON value (object, list, string, number, etc.)
            from the next frame.

        Raises:
            WebSocketDisconnect: When the client closes the connection
                before a frame is received.
        """
        import json

        if mode == "text":
            text = await self.receive_text()
            return json.loads(text)
        data = await self.receive_bytes()
        return json.loads(data)

    async def send_text(self, data: str) -> None:
        """Send a text frame to the client.

        Args:
            data: The text payload to send.
        """
        await self._send({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        """Send a binary frame to the client.

        Args:
            data: The raw bytes to send.
        """
        await self._send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any, mode: str = "text") -> None:
        """Serialise ``data`` as JSON and send it as a single frame.

        Args:
            data: The JSON-serialisable value to send.
            mode: ``"text"`` (default) sends a text frame. ``"binary"``
                sends a binary frame with the JSON encoded as UTF-8.
        """
        import json

        text = json.dumps(data)
        if mode == "text":
            await self.send_text(text)
        else:
            await self.send_bytes(text.encode("utf-8"))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the WebSocket with the given status code and reason.

        Args:
            code: WebSocket close status code (default ``1000`` for a
                normal closure).
            reason: Optional human-readable reason that the peer will
                receive in the close frame.
        """
        await self._send({"type": "websocket.close", "code": code, "reason": reason})
