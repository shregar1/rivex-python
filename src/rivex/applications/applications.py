from __future__ import annotations

import asyncio
import inspect
import json
import os
import signal
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path as Pathlib
from types import SimpleNamespace
from typing import Any

import rivex_core
from rivex.di._injection import build_handler_wrapper
from rivex.web.routing import Controller, Router, RouteRecord, controller_to_router, is_controller


def _make_hook_middleware(
    before: list,
    after: list,
    after_resp: list,
) -> Any:
    """Build a Middleware subclass that runs the given hook lists.

    Defined as a factory (rather than a closure that creates a new
    class) so the class itself only exists once per ``(before,
    after, after_resp)`` triple -- repeated ``run()`` calls no longer
    leak class objects into the GC heap.
    """
    from rivex.middleware.middleware import Middleware

    class _HookMiddleware(Middleware):
        async def process(self, request_data, call_next):
            """Run this middleware's ``before`` hooks, forward to the chain, then run ``after`` hooks.

            Each ``before`` hook may return a dict to short-circuit
            the response, or a coroutine that resolves to one.
            Each ``after`` hook may replace the response with its
            own dict. ``after_resp`` hooks are fire-and-forget and
            their exceptions are logged-and-suppressed so they
            cannot fail an otherwise-successful request.

            Args:
                request_data: The in-flight request envelope.
                call_next: Awaitable invoking the downstream chain.

            Returns:
                The response dict after all hook stages have run.
            """
            import asyncio as _aio

            for hook in before:
                result = hook(request_data)
                if _aio.iscoroutine(result):
                    result = await result
                if isinstance(result, dict):
                    return result

            response = await call_next(request_data)

            for hook in after:
                modified = hook(request_data, response)
                if _aio.iscoroutine(modified):
                    modified = await modified
                if isinstance(modified, dict):
                    response = modified

            for hook in after_resp:
                try:
                    result = hook(request_data, response)
                    if _aio.iscoroutine(result):
                        await result
                except Exception:
                    pass

            return response

    return _HookMiddleware


def _run_coroutine_sync(coro: Any) -> Any:
    """Drive a coroutine to completion from a synchronous call site.

    Works correctly in all four contexts:

    1. No event loop on this thread (typical sync test setup):
       use ``asyncio.run``.
    2. Event loop exists but is not running: use ``run_until_complete``.
    3. Event loop is running on this thread (the common request
       handler / lifespan case): we cannot call ``run_until_complete``
       on the same thread (it would deadlock) and ``asyncio.run`` is
       forbidden from a running loop. Spin up a fresh loop on a
       worker thread and drive the coroutine there.
    4. Event loop is running on a different thread: same as (3) --
       we run on a worker thread with its own loop to stay
       independent of the callers loop.

    Returns the coroutines result.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(coro)

    if not loop.is_running():
        return loop.run_until_complete(coro)

    # A loop is running on this thread. We cant use
    # ``asyncio.run_coroutine_threadsafe`` from this thread either
    # -- the future would never resolve because the loop is blocked
    # waiting for us. The safe path is to drive the coroutine on a
    # fresh worker thread with its own loop.
    import threading

    holder: dict[str, Any] = {}

    def _worker() -> None:
        """Drive ``coro`` to completion on a fresh worker thread.

        Used by :func:`_run_coroutine_sync` when an event loop is
        already running on the calling thread. Runs
        :func:`asyncio.run` on its own daemon thread so neither
        the caller's loop nor a potential deadlock between
        threads can stop the coroutine from completing. The
        result (or any raised exception) is stashed in the
        enclosing ``holder`` dict.
        """
        try:
            holder["result"] = asyncio.run(coro)
        except BaseException as e:  # noqa: BLE001
            holder["error"] = e

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join()
    if "error" in holder:
        raise holder["error"]
    return holder.get("result")


class Rivex:
    """The main Rivex application -- owns routes, middleware, exception handlers, and lifecycle.

    A typical app is built by decorating async functions with ``@app.get`` /
    ``@app.post`` / etc., optionally registering controllers and middleware.
    Once the routes are wired up, call :meth:`run` to start the server.

    Example::

        from rivex import Rivex, Path

        app = Rivex(title="My API", version="1.0.0")

        @app.get("/items/{item_id}")
        async def get_item(item_id: int = Path(ge=1)):
            return {"id": item_id}

        if __name__ == "__main__":
            app.run(host="0.0.0.0", port=8000)

    The class also accepts a long list of constructor options that mirror
    the OpenAPI metadata, server lifecycle, branding, and admin dashboard
    configuration. See the parameter list below.
    """

    def __init__(
        self,
        title: str = "Rivex",
        version: str = "0.1.0",
        description: str | None = None,
        debug: bool = False,
        docs_url: str | None = "/docs",
        redoc_url: str | None = "/redoc",
        openapi_url: str | None = "/openapi.json",
        openapi_tags: list[dict[str, Any]] | None = None,
        servers: list[dict[str, Any]] | None = None,
        terms_of_service: str | None = None,
        contact: dict[str, Any] | None = None,
        license_info: dict[str, Any] | None = None,
        lifespan: Callable | None = None,
        logo_url: str | None = None,
        favicon_url: str | None = None,
        health_url: str | None = "/",
        liveness_url: str | None = None,
        readiness_url: str | None = None,
        shutdown_timeout: int = 30,
        drain_timeout: int | None = None,
        max_body_size: int | None = None,
        app_name: str | None = None,
        powered_by: str | None = None,
        admin_url: str | None = None,
        admin_token: str | None = None,
        admin_db: str | Pathlib | None = None,
        landing_page: bool = True,
        asyncapi_url: str | None = "/asyncapi.json",
        asyncapi_docs_url: str | None = "/asyncapi",
        template_dir: str | None = None,
    ):
        """Construct a new Rivex application.

        Args:
            title: Application title shown in OpenAPI / docs UI.
            version: Semantic version string for the OpenAPI document.
            description: Long-form description for the OpenAPI document.
            debug: When ``True``, surface unhandled exceptions as 500s with
                the original message instead of the generic envelope.
            docs_url: Path for the Swagger UI; ``None`` disables it.
            redoc_url: Path for ReDoc; ``None`` disables it.
            openapi_url: Path that serves the raw OpenAPI JSON; ``None`` disables it.
            openapi_tags: Tag definitions used to group operations in the docs UI.
            servers: ``servers`` entries for the OpenAPI document.
            terms_of_service: URL for the OpenAPI ``termsOfService`` field.
            contact: ``contact`` block for the OpenAPI document.
            license_info: ``license`` block for the OpenAPI document.
            lifespan: Optional context manager called on startup / shutdown.
            logo_url: Logo URL shown on the landing / docs pages.
            favicon_url: Favicon URL.
            health_url: Path for the bundled health endpoint (``GET`` returns 200).
            liveness_url: Optional dedicated liveness probe path.
            readiness_url: Optional dedicated readiness probe path.
            shutdown_timeout: Seconds to wait for in-flight requests on shutdown.
            drain_timeout: Optional separate drain timeout; defaults to ``shutdown_timeout``.
            max_body_size: Reject request bodies larger than this (bytes).
            app_name: Override the brand mark shown on the landing page.
            powered_by: Override the "powered by" attribution. ``""`` hides it.
            admin_url: Mount the admin dashboard at this path; ``None`` (default) disables it.
            admin_token: Static token required to access the admin dashboard.
            admin_db: Path to a SQLite DB that stores admin users + hashed tokens.
            landing_page: When ``True`` (default), serve a bare-bones HTML page
                at ``GET /`` if the user hasnt registered their own route.
            asyncapi_url: Path that serves the raw AsyncAPI JSON; ``None`` disables it.
            asyncapi_docs_url: Path for the AsyncAPI UI; ``None`` disables it.
            template_dir: Optional directory of HTML templates for the frameworks
                templating helpers.
        """
        self.title = title
        self.version = version
        self.description = description
        self.debug = debug
        self.docs_url = docs_url
        self.redoc_url = redoc_url
        self.openapi_url = openapi_url
        self.openapi_tags = openapi_tags
        self.servers = servers
        self.terms_of_service = terms_of_service
        self.contact = contact
        self.license_info = license_info
        self.lifespan = lifespan
        self.logo_url = logo_url
        self.favicon_url = favicon_url
        self.health_url = health_url
        self.liveness_url = liveness_url
        self.readiness_url = readiness_url
        self.shutdown_timeout = shutdown_timeout
        self.drain_timeout = drain_timeout if drain_timeout is not None else shutdown_timeout
        self.max_body_size = max_body_size
        # `app_name` overrides the big brand mark on the landing / docs pages.
        # Defaults to the framework name "Rivex" so existing apps see no change.
        self.app_name = app_name or "Rivex"
        # `powered_by` is the small attribution under / next to the brand.
        # `None` means "powered by Rivex" (the framework); pass an empty
        # string to suppress the attribution entirely.
        self.powered_by = "Rivex" if powered_by is None else powered_by
        # Admin dashboard. `None` (default) means "do not mount"; pass a path
        # to mount at that path. `admin_token` enables auth on the
        # dashboard for a single static token (back-compat).  Prefer
        # `admin_db` -- when set, the dashboard looks up users + hashed
        # tokens in the SQLite DB at this path.  Default for ``admin_db``
        # is ``./.rivex/admin.db`` (overridable via ``RIVEX_ADMIN_DB``).
        self.admin_url = admin_url
        self.admin_token = admin_token
        self.admin_db = admin_db
        self.asyncapi_url = asyncapi_url
        self.asyncapi_docs_url = asyncapi_docs_url
        self.template_dir = template_dir
        self._templates: Any = None
        # ``landing_page`` controls whether Rivex auto-mounts a
        # bare-bones HTML page at ``GET /`` when the user hasnt
        # registered their own route there.  Default ``True`` so
        # users with only ``pip install rivex`` see something
        # useful on first run.  Set to ``False`` to opt out (e.g.
        # when serving the route from another framework).
        self.landing_page = landing_page
        self.state = SimpleNamespace()
        # Database registry -- configure via ``app.db.configure(...)``.
        # Pools are connected automatically by the lifefan hook or
        # manually via ``await app.db.connect_all()``.
        from rivex.db import DatabaseRegistry

        self._db: DatabaseRegistry = DatabaseRegistry()
        # Tier 1 security config (CORS, CSRF, HSTS, trusted hosts,
        # XSS escaping, body size limit). Set via ``app.security = ...``
        # (dict) or by passing ``security=`` to the constructor.
        # The dict is forwarded to the Rust core on the next
        # ``run*()`` call.
        self._security_config: dict[str, Any] | None = None
        # The async/hyper Rust server -- used by ``run()`` and
        # ``run_async()`` (both are equivalent for the default path,
        # ``run()`` is the ASGI-flavoured alias kept for FastAPI muscle
        # memory).
        self._server = rivex_core.RivexServer()
        # The sync std::thread-based Rust server -- used by
        # ``run_sync()``. Has lower per-request latency than the async
        # server on CPU-bound pure-Python handlers (no async runtime
        # overhead, no GIL churn from coroutine scheduling) but no
        # streaming and no HTTP/2.
        self._sync_server = rivex_core.RivexSyncServer()
        # The active server mode is decided per ``run*()`` call.
        self._routes: list[RouteRecord] = []
        self._ws_routes: list[tuple[str, Callable]] = []
        self._mounts: list[tuple[str, Any]] = []
        self._middleware: list[tuple[type | Callable, dict[str, Any]]] = []
        self._startup_hooks: list[Callable] = []
        self._shutdown_hooks: list[Callable] = []
        self._before_request_hooks: list[Callable] = []
        self._after_request_hooks: list[Callable] = []
        self._after_response_hooks: list[Callable] = []
        self._exception_handlers: dict[type, Callable] = {}
        self._fallback_handler: Callable | None = None
        self._plugins: dict[str, Any] = {}
        self.dependency_overrides: dict[Callable, Callable] = {}

        # Auto-mount the admin dashboard if requested. The dashboard is a
        # zero-build HTMX + Alpine.js SPA that ships with the framework.
        if self.admin_url:
            self._mount_admin(self.admin_url, self.admin_token)

    # ── route decorators ──

    def get(self, path: str, **kwargs: Any) -> Callable:
        """Register a ``GET`` route.

        Args:
            path: URL pattern (e.g. ``"/items/{item_id}"``).
            **kwargs: Forwarded to :meth:`_route` -- see that methods docstring
                for the full list of supported options (status_code,
                response_model, tags, summary, etc.).
        Returns:
            A decorator that registers the wrapped async function as the handler.
        """
        return self._route("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable:
        """Register a ``POST`` route. See :meth:`_route` for supported options."""
        return self._route("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Callable:
        """Register a ``PUT`` route. See :meth:`_route` for supported options."""
        return self._route("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Callable:
        """Register a ``DELETE`` route. See :meth:`_route` for supported options."""
        return self._route("DELETE", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Callable:
        """Register a ``PATCH`` route. See :meth:`_route` for supported options."""
        return self._route("PATCH", path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> Callable:
        """Register a ``HEAD`` route. See :meth:`_route` for supported options."""
        return self._route("HEAD", path, **kwargs)

    def options(self, path: str, **kwargs: Any) -> Callable:
        """Register an ``OPTIONS`` route. See :meth:`_route` for supported options."""
        return self._route("OPTIONS", path, **kwargs)

    # ── const-route (pre-baked) registrations ──

    def add_const_route(
        self,
        method: str,
        path: str,
        status: int = 200,
        body: bytes | str = b"",
        headers: list[tuple[str, str]] | dict[str, str] | None = None,
    ) -> None:
        """Register a **const (pre-baked) response** for a static route.

        The response is replayed verbatim for every matching request:
        no Python is touched, no matchit trie walk happens, and the
        worker pool is bypassed. Use for hot static endpoints like
        ``/health``, ``/metrics``, and small OpenAPI documents.

        ``method`` and ``path`` must be exact (no path parameters).
        The route is registered on both the async and sync engines --
        the call to ``run*()`` decides which one actually serves it.

        Example:

        .. code-block:: python

            app.add_const_route("GET", "/health", status=200, body=b"OK")
            app.add_const_route(
                "GET", "/version", status=200, body={"v": "1.0"},
                headers={"content-type": "application/json"},
            )
        """
        if "{" in path or "}" in path:
            raise ValueError(
                "const_route does not support path parameters "
                f"(got {path!r}); use @app.get() instead"
            )
        if isinstance(body, str):
            body_bytes: bytes = body.encode("utf-8")
        else:
            body_bytes = body
        if headers is not None and isinstance(headers, dict):
            headers = list(headers.items())
        self._server.add_const_route(method, path, status, body_bytes, headers)
        self._sync_server.add_const_route(method, path, status, body_bytes, headers)

    def _route(
        self,
        method: str,
        path: str,
        *,
        status_code: int = 200,
        response_model: Any = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        operation_id: str | None = None,
        deprecated: bool = False,
        include_in_schema: bool = True,
        openapi_extra: dict[str, Any] | None = None,
        responses: dict[int, dict[str, Any]] | None = None,
        response_model_include: set[str] | None = None,
        response_model_exclude: set[str] | None = None,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        name: str | None = None,
        cache_ttl: int | None = None,
        host: str | None = None,
        middleware: list[Any] | None = None,
    ) -> Callable:
        """Register a route on this application.

        Args:
            method: HTTP verb in uppercase (``"GET"``, ``"POST"``, ...).
            path: URL pattern with optional ``{path_params}``.
            status_code: Default response status when the handler returns normally.
            response_model: Pydantic / dataclass / type used for OpenAPI
                response schema and (optionally) response validation.
            tags: OpenAPI tags attached to this operation.
            summary: Short summary for the OpenAPI operation.
            description: Long description for the OpenAPI operation.
            operation_id: Unique identifier for the operation.
            deprecated: When ``True``, mark the operation as deprecated.
            include_in_schema: When ``False``, omit from the OpenAPI document.
            openapi_extra: Extra keys merged into the OpenAPI operation object.
            responses: Custom OpenAPI responses keyed by status code.
            response_model_include: Fields to include when serialising the
                response model (``None`` means all).
            response_model_exclude: Fields to exclude when serialising the response.
            response_model_exclude_unset: Drop fields that werent set.
            response_model_exclude_defaults: Drop default-valued fields.
            response_model_exclude_none: Drop ``None`` fields.
            name: Optional URL-for-reverse-lookup name.
            cache_ttl: When set, cache successful responses for this many seconds.
            host: Optional virtual-host restriction for this route.
            middleware: Optional per-route middleware stack.
        Returns:
            A decorator that registers the wrapped function as a handler.
        """
        if middleware is not None:
            for item in middleware:
                if isinstance(item, str) or not (isinstance(item, (type, tuple)) or callable(item)):
                    raise TypeError(f"Invalid middleware entry: {item!r}")

        def decorator(func: Callable) -> Callable:
            """Register ``func`` as a handler for the method+path combo on the parent ``_route`` call.

            Builds a :class:`RouteRecord` carrying the route's
            metadata (method, path, middleware, status code,
            response model, tags, OpenAPI extras, etc.) and
            appends it to the owning application's ``_routes``
            list. ``func`` is returned unchanged so further
            decorators can be stacked on top of it.

            Args:
                func: The handler function to register.

            Returns:
                The same ``func``, untouched, so the decorator
                is transparent to the rest of the user's
                decorator chain.
            """
            record = RouteRecord(
                method=method,
                path=path,
                endpoint=func,
                middleware=middleware,
                status_code=status_code,
                response_model=response_model,
                tags=tags or [],
                summary=summary,
                description=description,
                operation_id=operation_id,
                deprecated=deprecated,
                include_in_schema=include_in_schema,
                openapi_extra=openapi_extra,
                responses=responses,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                name=name,
                cache_ttl=cache_ttl,
                host=host,
            )
            self._routes.append(record)
            return func

        return decorator

    def url_for(self, name: str, **path_params: Any) -> str:
        """Resolve a named route's path template with the given path params.

        Performs a substring substitution of ``{key}`` placeholders
        in the matched route's template — it does **not** URL-encode
        values, so callers are responsible for pre-escaping any
        user-controlled input.

        Args:
            name: The route's ``name`` attribute (set via the
                ``name=`` kwarg on the route decorator).
            **path_params: Values for the route's path placeholders.

        Returns:
            The fully-substituted URL path string.

        Raises:
            ValueError: When no registered route has the given
                ``name``.
        """
        for route in self._routes:
            if route.name == name:
                path = route.path
                for key, value in path_params.items():
                    path = path.replace(f"{{{key}}}", str(value))
                return path
        raise ValueError(f"No route named {name}")

    @property
    def routes(self) -> list[RouteRecord]:
        """Return a snapshot copy of the application's registered routes.

        Returns:
            A new list containing every :class:`RouteRecord`
            currently registered with this app. Mutating the
            returned list does not affect the app's internal
            registry.
        """
        return list(self._routes)

    def group(
        self, prefix: str = "", tags: list[str] | None = None, middleware: list | None = None
    ):
        """Return a :class:`RouteGroup` bound to this app for shared prefix/tags/middleware.

        The returned group exposes the same ``get`` / ``post`` /
        ``route`` decorator surface as the app, but every route
        registered through it inherits the supplied ``prefix``,
        ``tags``, and ``middleware``. Routes still go into the
        parent app's ``_routes`` list so they are served normally.

        Args:
            prefix: Path prefix prepended to every route in the
                group (e.g. ``"/api/v1"``).
            tags: Optional OpenAPI tags applied to every route in
                the group.
            middleware: Optional per-route middleware applied to
                every route in the group.

        Returns:
            A :class:`RouteGroup` configured with the supplied
            metadata and bound to this app.
        """
        from rivex.web.routing import RouteGroup

        class _AppRouterShim:
            def __init__(shim, app):
                shim.prefix = ""
                shim.tags = []
                shim._routes = app._routes
                shim._middleware = []
                shim._exception_handlers = app._exception_handlers

        shim = _AppRouterShim(self)
        grp = RouteGroup(shim, prefix=prefix, tags=tags or [], middleware=middleware or [])  # type: ignore[arg-type]
        return grp

    # ── websocket ──

    def websocket(self, path: str) -> Callable:
        """Register a WebSocket handler bound to *path*.

        Usage::

            @app.websocket("/ws")
            async def ws(socket): ...

        The handler receives a Rivex WebSocket object and must
        use its ``send`` / ``receive`` coroutines (or the helpers
        ``send_text`` / ``send_json``) to drive the connection.

        Args:
            path: The WebSocket endpoint path.

        Returns:
            A decorator that registers the wrapped async
            function as the handler for the endpoint.
        """
        def decorator(func: Callable) -> Callable:
            """Append ``func`` to ``self._ws_routes`` and return it unchanged."""
            self._ws_routes.append((path, func))
            return func

        return decorator

    # ── server-sent events (SSE) ──

    def sse(self, path: str, **kwargs: Any) -> Callable:
        """Register an SSE endpoint.

        The decorated function should be an **async generator** that
        yields :class:`~rivex.sse.SSEEvent` objects (or plain strings
        that are valid SSE frames)::

            @app.sse("/events")
            async def event_stream():
                yield SSEEvent(data="hello")
                await asyncio.sleep(1)
                yield SSEEvent(data="world", event="update")

        The handler is wrapped in an
        :class:`~rivex.responses.EventSourceResponse` so the Rust core
        streams each event as a separate chunk over the HTTP connection
        with ``Content-Type: text/event-stream``.
        """

        from rivex.http.responses import EventSourceResponse
        from rivex.web.routing import RouteRecord

        def _coerce_sse(gen: Any) -> Any:
            """Wrap a generator so ``SSEEvent`` objects are
            formatted into SSE text before the Rust streaming
            pipeline sees them."""
            if hasattr(gen, "__aiter__"):
                async def _awrap():
                    """Wrap an async generator, formatting each event into an SSE text chunk."""
                    async for ev in gen:
                        if isinstance(ev, str):
                            yield ev
                        elif hasattr(ev, "_format"):
                            yield ev._format()
                        else:
                            yield str(ev)
                return _awrap()
            # Sync generator fallback
            def _wrap():
                """Wrap a sync generator, formatting each event into an SSE text chunk."""
                for ev in gen:
                    if isinstance(ev, str):
                        yield ev
                    elif hasattr(ev, "_format"):
                        yield ev._format()
                    else:
                        yield str(ev)
            return _wrap()

        def decorator(func: Callable) -> Callable:
            """Register *func* as the generator backing an SSE endpoint.

            Wraps the user-provided generator in a small
            request-to-raw-response adapter that pulls ``path_params``
            out of ``request_data`` and feeds them to the
            generator. The wrapped ``sse_handler`` is registered
            as a GET ``RouteRecord`` so the rest of the framework
            sees a normal HTTP route.

            Args:
                func: The user's generator function. May be sync,
                    async, or an async generator.

            Returns:
                The internal ``sse_handler`` wrapper that the
                framework will call at request time.
            """
            # SSE handler directly extracts path params from the
            # request_data dict the Rust core passes. It bypasses
            # build_handler_wrapper so path params reach the generator.
            async def sse_handler(request_data: dict) -> dict:
                """Bridge a single SSE request from the framework to the user generator.

                Pulls ``path_params`` out of ``request_data``,
                invokes the user function, awaits a coroutine if
                one was returned, normalises whatever iterator
                came back via :func:`_coerce_sse`, and returns a
                raw ``EventSourceResponse`` payload the Rust
                core can stream.

                Args:
                    request_data: The framework-provided request
                        envelope.

                Returns:
                    The raw event-source response payload as a
                    dict, suitable for the streaming pipeline.
                """
                path_params = request_data.get("path_params", {})
                raw = func(**path_params)
                # ``func`` may be sync, async, or an async generator.
                # In all three cases the SSE stream must be a real
                # iterator of SSE-formatted chunks, not a coroutine or
                # async-generator object that nobody awaits.
                if inspect.isawaitable(raw):
                    raw = await raw
                formatted = _coerce_sse(raw)
                resp = EventSourceResponse(content=formatted)
                return resp._to_raw()
            sse_handler._rivex_sse_handler = True
            self._routes.append(
                RouteRecord(
                    method="GET",
                    path=path,
                    endpoint=sse_handler,
                    status_code=kwargs.pop("status_code", 200),
                    response_model=kwargs.pop("response_model", None),
                    tags=kwargs.pop("tags", []),
                    summary=kwargs.pop("summary", None),
                    description=kwargs.pop("description", None),
                    operation_id=kwargs.pop("operation_id", None),
                    deprecated=kwargs.pop("deprecated", False),
                    include_in_schema=kwargs.pop("include_in_schema", True),
                )
            )
            return sse_handler

        return decorator

    # ── mount ──

    def mount(self, path: str, app: Any) -> None:
        """Mount a sub-application at *path*.

        Useful for serving static files, an admin dashboard, or another
        ASGI-compatible framework under a path prefix.

        Args:
            path: Mount point (e.g. ``"/static"`` or ``"/admin"``).
            app: Sub-application -- typically an ASGI 3 instance or an
                object that exposes ``_routes`` (e.g. a :class:`Rivex` app
                or a StaticFiles handler).
        """
        path = path.rstrip("/")
        self._mounts.append((path, app))
        # Merge the sub-apps HTTP routes with the prefix
        if hasattr(app, "_routes"):
            for route in app._routes:
                merged = RouteRecord(
                    method=route.method,
                    path=path + route.path,
                    endpoint=route.endpoint,
                    status_code=route.status_code,
                    response_model=route.response_model,
                    tags=route.tags,
                    summary=route.summary,
                    description=route.description,
                    operation_id=route.operation_id,
                    deprecated=route.deprecated,
                    include_in_schema=route.include_in_schema,
                    openapi_extra=route.openapi_extra,
                    responses=route.responses,
                    response_model_include=route.response_model_include,
                    response_model_exclude=route.response_model_exclude,
                    response_model_exclude_unset=route.response_model_exclude_unset,
                    response_model_exclude_defaults=route.response_model_exclude_defaults,
                    response_model_exclude_none=route.response_model_exclude_none,
                    name=route.name,
                    middleware=route.middleware,
                    exception_handlers=route.exception_handlers,
                    validate_response=route.validate_response,
                    cache_ttl=route.cache_ttl,
                    host=route.host,
                )
                self._routes.append(merged)
        # Merge the sub-apps WebSocket routes with the prefix
        if hasattr(app, "_ws_routes"):
            for ws_path, ws_handler in app._ws_routes:
                self._ws_routes.append((path + ws_path, ws_handler))

    # ── plugins ──

    def register_plugin(self, plugin: Any) -> None:
        """Install *plugin* into this app and remember it by name.

        The plugin's :meth:`~rivex.cli.plugins.Plugin.install` is
        called immediately so it can attach routes, middleware,
        or hooks before the server starts. The plugin is then
        stored in :attr:`_plugins` keyed by ``plugin.name`` (or
        the class name when ``name`` is empty) for later lookup
        via :meth:`get_plugin`.

        Args:
            plugin: A :class:`rivex.cli.plugins.Plugin` instance.

        Raises:
            TypeError: When *plugin* is not a ``Plugin`` subclass
                instance.
        """
        from rivex.cli.plugins import Plugin

        if not isinstance(plugin, Plugin):
            raise TypeError(f"Expected Plugin instance, got {type(plugin)}")
        name = plugin.name or type(plugin).__name__
        plugin.install(self)
        self._plugins[name] = plugin

    def get_plugin(self, name: str) -> Any:
        """Return the plugin previously registered under *name*.

        Args:
            name: The plugin's ``name`` attribute, or its class
                name when ``name`` was left empty at install time.

        Returns:
            The :class:`Plugin` instance, or ``None`` when no
            plugin is registered under that key.
        """
        return self._plugins.get(name)

    # ── router inclusion ──

    def include_router(
        self,
        router: Router | type[Controller] | Controller,
        *,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Register every route from a :class:`Router` or :class:`Controller` on this app.

        Each route path is prefixed with *prefix*, and the route tags
        are merged with *tags*. The routers own middleware + lifecycle
        hooks are preserved.

        Args:
            router: A :class:`Router`, a :class:`Controller` class, or a
                :class:`Controller` instance.
            prefix: Optional URL prefix applied to every route (e.g. ``"/v1"``).
            tags: Optional tags prepended to every routes tags.
        Raises:
            TypeError: If *router* is neither a Router nor a Controller.
        """
        if is_controller(router):
            router = controller_to_router(router)  # type: ignore[arg-type]
        if not isinstance(router, Router):
            raise TypeError(
                f"include_router expected a Router (or Controller), "
                f"got {type(router).__name__}: {router!r}"
            )

        from rivex.web.routing import _LifecycleHookMiddleware

        hook_mw: list[tuple[type, dict]] = []
        before_hooks = getattr(router, "_before_request_hooks", [])
        after_hooks = getattr(router, "_after_request_hooks", [])
        if before_hooks or after_hooks:
            hook_mw.append(
                (
                    _LifecycleHookMiddleware,
                    {
                        "before": list(before_hooks),
                        "after": list(after_hooks),
                    },
                )
            )
        router_mw = getattr(router, "_middleware", [])
        combined_mw = list(hook_mw) + list(router_mw)

        for record in router._routes:
            route_mw = list(combined_mw) + (record.middleware or [])
            merged = RouteRecord(
                method=record.method,
                path=prefix + record.path,
                endpoint=record.endpoint,
                status_code=record.status_code,
                response_model=record.response_model,
                tags=(tags or []) + record.tags,
                summary=record.summary,
                description=record.description,
                operation_id=record.operation_id,
                deprecated=record.deprecated,
                include_in_schema=record.include_in_schema,
                openapi_extra=record.openapi_extra,
                responses=record.responses,
                response_model_include=record.response_model_include,
                response_model_exclude=record.response_model_exclude,
                response_model_exclude_unset=record.response_model_exclude_unset,
                response_model_exclude_defaults=record.response_model_exclude_defaults,
                response_model_exclude_none=record.response_model_exclude_none,
                name=record.name,
                middleware=route_mw if route_mw else None,
                exception_handlers=record.exception_handlers,
                validate_response=record.validate_response,
                cache_ttl=record.cache_ttl,
                host=record.host,
            )
            self._routes.append(merged)

        if any(getattr(r, "access_key", None) for r in router._routes):
            self._install_access_key_middleware_if_needed()

    def include_controller(
        self,
        controller: type[Controller] | Controller,
        *,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Register a :class:`Controller` (or Controller class) on this app.

        Shorthand for :meth:`include_router` for the controller case.
        See that method for parameter semantics.
        """
        self.include_router(controller, prefix=prefix, tags=tags)

    def include_route(
        self,
        method: str,
        path: str,
        endpoint: Callable,
        *,
        name: str | None = None,
        prefix: str = "",
        status_code: int = 200,
        request_dto: Any = None,
        response_dto: Any = None,
        response_model: Any = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        operation_id: str | None = None,
        deprecated: bool = False,
        include_in_schema: bool = True,
        access_key: str | None = None,
        openapi_extra: dict[str, Any] | None = None,
        responses: dict[int, dict[str, Any]] | None = None,
        response_model_include: set[str] | None = None,
        response_model_exclude: set[str] | None = None,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        middleware: list[tuple[type, dict]] | None = None,
        exception_handlers: dict[type, Callable] | None = None,
        validate_response: bool = False,
        cache_ttl: int | None = None,
        host: str | None = None,
    ) -> RouteRecord:
        """Register a single route on this app without a Controller or Router.

        Eagerly wires :class:`AccessKeyMiddleware` (if not already wired)
        the moment any route declares an ``access_key`` so the ASGI
        adapter enforces it regardless of whether ``run()`` /
        ``run_async()`` / external ``uvicorn`` is used.

        One-off registration for health checks, webhooks, decorator-injected
        handlers, and any other route that doesn't justify a full
        Controller class. The route inherits any app-level middleware
        already installed via :meth:`add_middleware`.

        Returns the created :class:`RouteRecord` so callers can introspect
        or override metadata later.

        Parameters:
            method: HTTP method (``"GET"``, ``"POST"``, …, case-insensitive).
            path: Route path. *prefix* (if any) is prepended.
            endpoint: Callable handling the request.
            name: Stable route name (used by ``url_for(name, **params)``
                and OpenAPI ``operationId`` when ``operation_id`` is unset).
            prefix: URL prefix appended to ``path`` (e.g. ``"/v1"``).
            status_code: Default ``200``; can be any 2xx for endpoint success.
            request_dto: pydantic / dataclass used for body validation
                and OpenAPI request schema.
            response_dto: pydantic / dataclass used for response
                serialisation. ``response_model`` is accepted as an alias.
            tags: Tags for OpenAPI grouping (merged with app defaults).
            summary / description / operation_id: OpenAPI metadata.
            deprecated / include_in_schema: OpenAPI flags.
            access_key: When set, the framework rejects requests whose
                ``X-Access-Key`` header doesn't match. Useful for per-API-user
                authorisation on internal endpoints.
            openapi_extra: Free-form OpenAPI extras dict.
            responses: Override the default OpenAPI ``responses`` map
                (``{ status_code: { ... } }``).
            response_model_include / response_model_exclude /
            response_model_exclude_unset / response_model_exclude_defaults /
            response_model_exclude_none: Pydantic serialisation knobs.
            middleware: Per-route middleware (applied after the app-level
                ones). ``None`` for no per-route additions.
            exception_handlers: Per-route exception handler overrides.
            validate_response: When ``True`` the framework validates the
                handler return value against ``response_dto``.
            cache_ttl: Seconds to cache the rendered response.
            host: Restrict the route to one host (``Host`` header).
        """
        from rivex.web.routing import RouteRecord

        full_path = prefix + path
        record = RouteRecord(
            method=method.upper(),
            path=full_path,
            endpoint=endpoint,
            name=name,
            status_code=status_code,
            request_dto=request_dto,
            response_dto=response_dto,
            response_model=response_model,
            tags=list(tags or []),
            summary=summary,
            description=description,
            operation_id=operation_id,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            access_key=access_key,
            openapi_extra=openapi_extra,
            responses=responses,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            middleware=list(middleware) if middleware else None,
            exception_handlers=dict(exception_handlers) if exception_handlers else None,
            validate_response=validate_response,
            cache_ttl=cache_ttl,
            host=host,
        )
        self._routes.append(record)
        if access_key is not None:
            self._install_access_key_middleware_if_needed()
        return record

    # ── Tier 1 security (CORS / CSRF / HSTS / trusted hosts / XSS / body limit) ──

    @property
    def security(self) -> dict[str, Any] | None:
        """Currently-installed Tier 1 security config. ``None`` if no
        security middleware is installed. The config is a plain dict
        so it round-trips through pyo3 without any custom marshaler.
        Schema::

            {
                "cors": {
                    "allow_origins": ["https://example.com"],
                    "allow_methods": ["GET", "POST"],
                    "allow_headers": ["content-type"],
                    "expose_headers": [],
                    "allow_credentials": True,
                    "max_age": 86400,
                },
                "csrf": {
                    "header_name": "X-CSRF-Token",
                    "cookie_name": "XSRF-TOKEN",
                    "safe_methods": ["GET", "HEAD", "OPTIONS"],
                    "enforce": True,
                },
                "hsts": {
                    "max_age": 31536000,
                    "include_subdomains": True,
                    "preload": False,
                },
                "trusted_hosts": {
                    "allowed": ["example.com", "*.example.com"],
                    "enforce": True,
                },
                "xss": {
                    "auto_escape_html": True,
                },
                "max_body_size": 1048576,
            }

        Each tier is independent -- pass a partial dict to enable
        just one protection.
        """
        return self._security_config

    @security.setter
    def security(self, value: dict[str, Any] | None) -> None:
        """Install / replace the Tier 1 security config. Pass
        ``None`` to clear (no security middleware). The new config
        is applied on the next ``run*()`` call.

        Convenience: pass an instance of ``rivex.security.SecurityConfig``
        and it will be converted to the dict form for you.
        """
        if value is None:
            self._security_config = None
        elif isinstance(value, dict):
            self._security_config = value
        else:
            # Allow a SecurityConfig instance (or any object with a
            # ``.to_dict()`` method) to be passed.
            to_dict = getattr(value, "to_dict", None)
            if callable(to_dict):
                self._security_config = to_dict()
            else:
                raise TypeError(
                    "security must be a dict, None, or an object with a .to_dict() method"
                )

    # ── Database registry ──

    @property
    def db(self) -> Any:
        """Database registry for connection pools.

        Configure databases with ``app.db.configure(...)`` and access
        pools with ``app.db.pool("default")`` or ``app.db["default"]``.

        Pools are automatically connected during the lifespan startup
        and disconnected during shutdown.
        """
        return self._db

    @db.setter
    def db(self, value: Any) -> None:
        self._db = value

    def with_security(
        self,
        cors: dict[str, Any] | None = None,
        csrf: dict[str, Any] | None = None,
        hsts: dict[str, Any] | None = None,
        trusted_hosts: list[str] | None = None,
        xss: dict[str, Any] | None = None,
        max_body_size: int | None = None,
    ) -> Rivex:
        """Fluent builder for Tier 1 security config. Returns ``self``
        for chaining. Pass any subset of protections; omitted
        protections keep their previous value (or stay disabled
        if no previous value).

        Example::

            app.with_security(
                cors={"allow_origins": ["https://example.com"],
                      "allow_methods": ["GET", "POST"], "max_age": 86400},
                hsts={"max_age": 31_536_000, "preload": True},
                trusted_hosts=["example.com", "*.example.com"],
                max_body_size=1_048_576,
            )
        """
        cfg = dict(self._security_config) if self._security_config else {}
        if cors is not None:
            cfg["cors"] = cors
        if csrf is not None:
            cfg["csrf"] = csrf
        if hsts is not None:
            cfg["hsts"] = hsts
        if trusted_hosts is not None:
            cfg["trusted_hosts"] = {"allowed": trusted_hosts, "enforce": True}
        if xss is not None:
            cfg["xss"] = xss
        if max_body_size is not None:
            cfg["max_body_size"] = max_body_size
        self._security_config = cfg
        return self

    # ── middleware ──

    def add_middleware(self, middleware_cls: type, **kwargs: Any) -> None:
        """Register a middleware class on this app.

        FastAPI-style API: ``app.add_middleware(MyMiddleware, arg1=..., arg2=...)``.
        The framework instantiates ``MyMiddleware(**kwargs)`` at startup and
        wraps every request with it. For built-in observability middlewares
        the kwargs are also forwarded to the Rust core so the const-router
        fast path can apply them without going through Python.

        Args:
            middleware_cls: A middleware class implementing ``async def process(request_data, call_next)``.
            **kwargs: Keyword arguments forwarded to the middleware constructor.
        """
        # FastAPI-style: `app.add_middleware(Class, **kwargs)`.
        # Python classes are stored in `_middleware` and applied to
        # the ASGI dispatcher (uvicorn path). The Tier 2 builtin
        # observability classes below are ALSO recognised here and
        # the kwargs are forwarded to the Rust engine so the
        # const-router fast path benefits too.
        from rivex.middleware.middleware_auth import JWTAuthMiddleware as _JWTMW
        from rivex.middleware.middleware_observability import (
            HealthCheckMiddleware as _HealthMW,
        )
        from rivex.middleware.middleware_observability import (
            JsonLoggingMiddleware as _JsonMW,
        )
        from rivex.middleware.middleware_observability import (
            PrometheusMetricsMiddleware as _PromMW,
        )
        from rivex.middleware.middleware_observability import (
            TracingMiddleware as _TraceMW,
        )
        if middleware_cls is _PromMW:
            self._server.set_metrics(**kwargs)
            self._sync_server.set_metrics(**kwargs)
        elif middleware_cls is _TraceMW:
            self._server.set_tracing(**kwargs)
            self._sync_server.set_tracing(**kwargs)
        elif middleware_cls is _JsonMW:
            self._server.set_json_logging(**kwargs)
            self._sync_server.set_json_logging(**kwargs)
        elif middleware_cls is _HealthMW:
            self._server.set_health(**kwargs)
            self._sync_server.set_health(**kwargs)
        elif middleware_cls is _JWTMW:
            secret = kwargs.pop("secret")
            self._server.set_jwt_auth(secret=secret, **kwargs)
            self._sync_server.set_jwt_auth(secret=secret, **kwargs)
            return  # Rust pipeline only; skip Python middleware list
        self._middleware.append((middleware_cls, kwargs))

    def middleware(self, middleware_type: str) -> Callable:
        """FastAPI-compatible ``@app.middleware("http")`` decorator.

        Wraps a user function ``async def middleware(request, call_next)``
        into an internal :class:`_FuncMiddleware` so it can be
        inserted into the middleware chain. The framework handles
        converting the user's plain ``Response`` / dict return
        value into the raw envelope shape used downstream.

        Args:
            middleware_type: Currently only ``"http"`` is supported;
                any other value raises.

        Returns:
            A decorator that, when applied, registers the wrapped
            function as a per-request middleware.

        Raises:
            ValueError: When *middleware_type* is not ``"http"``.
        """
        if middleware_type != "http":
            raise ValueError(
                f"Unsupported middleware type \"{middleware_type}\". Only \"http\" is supported."
            )

        def decorator(func: Callable) -> Callable:
            """Register ``func`` as an HTTP middleware via an internal :class:`_FuncMiddleware` adapter."""
            from rivex.middleware.middleware import Middleware

            class _FuncMiddleware(Middleware):
                async def process(self, request_data: dict, call_next: Callable) -> dict:
                    """Adapt the user's middleware(request, call_next) shape to the framework's ``Middleware.process`` contract.

                    Builds a :class:`Request` from ``request_data``,
                    invokes *func* with a ``_next`` trampoline that
                    delegates to *call_next*, and normalises the
                    return value to the raw envelope dict.
                    """
                    from rivex.http.requests import Request

                    request = Request._from_raw(request_data)

                    async def _next(req: Any = None) -> dict:
                        """Forward to the downstream ``call_next`` and return its raw envelope."""
                        result: dict = await call_next(request_data)
                        return result

                    response = await func(request, _next)
                    if isinstance(response, dict):
                        return response
                    from rivex.http.responses import Response

                    if isinstance(response, Response):
                        return response._to_raw()
                    result: dict = response
                    return result

            self._middleware.append((_FuncMiddleware, {}))
            return func

        return decorator

    # ── lifecycle hooks ──

    def before_request(self, func: Callable) -> Callable:
        """Register a function to run before each request.

        The function receives request_data dict. If it returns a dict (response),
        the request is short-circuited and that response is returned immediately.

        Usage:
            @app.before_request
            async def check_maintenance(request_data):
                if MAINTENANCE_MODE:
                    return {"status": 503, "headers": [("content-type", "application/json")],
                            "body": b{"detail":"Maintenance"}}
        """
        self._before_request_hooks.append(func)
        return func

    def after_request(self, func: Callable) -> Callable:
        """Register a function to run after each request (before response is sent).

        The function receives (request_data, response) and can return a modified response dict.
        If it returns None, the original response is used.

        Usage:
            @app.after_request
            async def add_custom_header(request_data, response):
                response = dict(response)
                headers = list(response.get("headers", []))
                headers.append(("x-powered-by", "Rivex"))
                response["headers"] = headers
                return response
        """
        self._after_request_hooks.append(func)
        return func

    def after_response(self, func: Callable) -> Callable:
        """Register a function to run after the response has been sent.

        Fire-and-forget: exceptions are suppressed. Useful for cleanup, analytics, logging.
        The function receives (request_data, response).

        Usage:
            @app.after_response
            async def log_analytics(request_data, response):
                await analytics.track(request_data["path"], response["status"])
        """
        self._after_response_hooks.append(func)
        return func

    def on_event(self, event_type: str) -> Callable:
        """Decorator factory for lifecycle hooks.

        Args:
            event_type: Either ``"startup"`` or ``"shutdown"``. The
                decorated coroutine is awaited on the matching lifecycle
                transition.
        Returns:
            A decorator that registers the wrapped function.
        """
        def decorator(func: Callable) -> Callable:
            """Append ``func`` to the startup or shutdown hook list based on ``event_type``."""
            if event_type == "startup":
                self._startup_hooks.append(func)
            elif event_type == "shutdown":
                self._shutdown_hooks.append(func)
            return func

        return decorator

    # ── exception handlers ──

    def exception_handler(self, exc_class: type) -> Callable:
        """Decorator factory that registers a custom handler for *exc_class*.

        The wrapped function receives ``(request, exc)`` and may return
        either a Rivex ``Response`` object or a plain dict with
        ``status``/``headers``/``body``.

        Args:
            exc_class: The exception type (or one of its bases) to handle.
        Returns:
            A decorator that registers the wrapped function.
        """
        def decorator(func: Callable) -> Callable:
            """Register ``func`` as the handler for the matching ``exc_class`` and return it unchanged."""
            self._exception_handlers[exc_class] = func
            return func

        return decorator

    # ── custom fallback handler ──

    def fallback(self, handler: Callable) -> None:
        """Register a fallback handler invoked when no route matches.

        Args:
            handler: Callable receiving the raw :class:`Request` and returning
                a Rivex response.
        """
        self._fallback_handler = handler

    # ── server lifecycle ──

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        workers: int = 1,
        *,
        mode: str = "auto",
        reload: bool = False,
        log_level: str | None = None,
    ) -> None:
        """Start the Rivex native HTTP server and serve the app.

        Serves on the Rivex native async engine (hyper+Tokio). The Rust
        core owns the TCP socket, parses requests, serves const routes
        entirely in Rust (no Python boundary), and dispatches dynamic
        handlers to a Python worker thread pool.

        Supports HTTP/1, HTTP/2 with auto-negotiation, streaming responses
        (SSE, NDJSON, large files), and WebSockets on the same listener.

        ``workers`` > 1 spawns one process per CPU core (clamped to
        ``os.cpu_count()``) -- each process binds the same port via
        ``SO_REUSEPORT`` so the kernel load-balances incoming
        connections. The default is one worker so the framework is easy
        to embed in test suites; bump it via ``workers=8`` or
        ``RIVEX_WORKERS=8`` for production.

        Args:
            host: Interface to bind (e.g. ``"0.0.0.0"`` for all interfaces).
            port: TCP port to listen on.
            workers: Number of worker processes (``1`` by default; clamped to CPU count).
            mode: ``"auto"`` (default) picks the best engine, ``"async"`` uses the
                hyper/Tokio async core, ``"sync"`` uses the per-thread sync core.
            reload: When ``True``, watch the source tree and auto-reload on change.
            log_level: Log level passed to the Rust core (``"info"``, ``"debug"``, ...).
        """

        if mode in ("auto", "async", "sync"):
            # The native engines have no built-in reload. When requested,
            # delegate to the stdlib file watcher, which respawns this
            # script as a subprocess on source change. The subprocess is
            # tagged via ``RIVEX_RELOAD_CHILD`` so it does not re-arm the
            # watcher (avoids endless respawning).
            if reload and os.environ.get("RIVEX_RELOAD_CHILD") != "1":
                self._run_with_reload(host=host, port=port, mode=mode)
                return
            if mode in ("auto", "async"):
                self.run_async(host=host, port=port, workers=workers)
            else:
                self.run_sync(host=host, port=port, workers=workers)
        elif mode == "asgi":
            self._run_uvicorn(
                host=host,
                port=port,
                workers=workers,
                reload=reload,
                log_level=log_level,
            )
        else:
            raise ValueError(
                f"unknown mode: {mode!r} "
                "(expected auto, async, sync, or asgi)"
            )

    def _run_with_reload(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        *,
        mode: str = "auto",
    ) -> None:
        """Run the server under the stdlib-based file watcher.

        The watcher respawns this script (``sys.executable *sys.argv``)
        as a child and restarts it whenever a watched ``*.py`` file
        changes. The child re-enters ``run()`` with ``reload=True`` but
        is tagged via ``RIVEX_RELOAD_CHILD`` so it skips the watcher and
        serves directly, binding the same host/port from its own
        ``main`` block.
        """
        from rivex.cli.reload import run_with_reload

        run_with_reload(watch_paths=[Pathlib.cwd()])

    def _run_uvicorn(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        workers: int = 1,
        reload: bool = False,
        log_level: str | None = None,
    ) -> None:
        """Serve via uvicorn (ASGI) for drop-in middleware compatibility."""
        from rivex.contrib.uvicorn import serve

        serve(
            self,
            host=host,
            port=port,
            workers=workers,
            reload=reload,
            log_level=log_level,
        )

    def run_async(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        workers: int = 1,
    ) -> None:
        """Serve via the **async** Rust engine (hyper+Tokio).

        This is the recommended path for new apps. It supports HTTP/1,
        HTTP/2, streaming responses, and websockets. The Rust core
        owns the TCP socket, parses requests, and dispatches each one
        to a Python worker thread that runs the user handler.

        ``workers`` > 1 spawns one process per CPU core (clamped to
        ``os.cpu_count()``) -- each process binds the same port via
        ``SO_REUSEPORT`` so the kernel load-balances incoming
        connections. This breaks the GIL barrier and gives the best
        throughput on multi-core machines. The default is one worker
        so the framework is easy to embed in test suites; bump it
        via ``workers=8`` or ``RIVEX_WORKERS=8`` for production.

        Trade-offs vs :meth:`run_sync`:

        - + HTTP/1 + HTTP/2 with auto-negotiation.
        - + Streaming responses (SSE, NDJSON, large files).
        - + WebSockets (with WS upgrade on the same listener).
        - + Per-handler async support (``async def``) without
              running the user coroutine on a separate loop.
        - - A small per-request cost for the async runtime vs
              the bare-thread sync server.
        """
        if workers > 1:
            self._run_async_multi_process(host, port, workers)
            return

        self._run_rust_async_server(host, port)

    def _run_async_multi_process(self, host: str, port: int, workers: int) -> None:
        """Spawn ``workers`` processes, each running the async engine.

        All workers bind the same port via ``SO_REUSEPORT`` -- the
        kernel hashes the source 4-tuple and dispatches connections
        across the listening sockets. This is the same model uvicorn
        uses for ``--workers N`` and the same model Robyn uses for
        ``--processes N``.

        We spawn via ``fork`` so the in-memory route table is shared
        across all workers without re-importing the user app N
        times. Each child runs the same Rust engine against a copy
        of the parsed routes; the Rust listener uses ``SO_REUSEPORT``
        to bind the same port.
        """
        import multiprocessing
        import os
        import time

        if not hasattr(os, "fork"):
            raise RuntimeError("Rivex async workers require fork support on this platform")

        ctx = multiprocessing.get_context("fork")
        processes = [
            ctx.Process(
                target=self._async_worker_entry,
                args=(self._pickle_artifact(), host, port),
                daemon=False,
            )
            for _ in range(workers)
        ]
        for process in processes:
            process.start()
        try:
            # Wait for Ctrl-C / SIGTERM. Each child traps the signal
            # itself; we just sleep until something interrupts us.
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
            for process in processes:
                process.join(timeout=5)
            for process in processes:
                if process.is_alive():
                    process.kill()

    def _pickle_artifact(self) -> bytes:
        """Pickle the route table so forked workers can rebuild it.

        We cant pickle the Rivex app (it holds a Rust object), but
        we can pickle the data needed to rebuild one: the routes,
        middleware, exception handlers, and so on. The Rust core
        gets reinitialised in each child.
        """
        # The current implementation simply returns None; the child
        # re-imports the parent module via its ``__main__`` path.
        # This is the same trick uvicorn uses. Future work could
        # serialise just the routes dict for a faster fork.
        return b""

    def _async_worker_entry(self, _artifact: bytes, host: str, port: int) -> None:
        """Re-import the parent module and start its async server.

        Forked workers receive the parent interpreter state, so
        ``sys.modules`` already has the app loaded. We just find the
        ``Rivex`` instance and call ``run_async`` on it.

        For now we use the simple approach: each worker re-uses the
        ``RivexServer`` that was built by the parent (its a Rust
        object, not picklable, but its safe to re-use after fork
        because the route table is read-only at request time).
        """
        import sys

        # Find the ``Rivex`` instance in the parents module. We look at
        # ``sys.modules`` for any module that has an ``app`` attribute
        # bound to a ``Rivex`` instance. This is what uvicorns worker
        # process does -- it looks for ``app`` in ``sys.modules``.
        target = None
        for _mod_name, mod in list(sys.modules.items()):
            if mod is None:
                continue
            app = getattr(mod, "app", None)
            if isinstance(app, Rivex):
                target = app
                break
        if target is None:
            # Fall back: find the first Rivex in any modules globals.
            for _mod_name, mod in list(sys.modules.items()):
                if mod is None:
                    continue
                for attr_name in dir(mod):
                    try:
                        attr = getattr(mod, attr_name)
                    except Exception:
                        continue
                    if isinstance(attr, Rivex):
                        target = attr
                        break
                if target is not None:
                    break
        if target is None:
            raise SystemExit(
                "could not find a Rivex instance in any module; "
                "make sure your app is assigned to a module-level variable named app"
            )
        target.run_async(host=host, port=port, workers=1)

    def run_sync(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        workers: int = 1,
    ) -> None:
        """Serve via the **sync** Rust engine (std::thread + httparse).

        This is the original 0.1.x path: a thread pool in Rust owns
        the TCP socket, parses requests, and dispatches each one to
        a Python worker thread that runs the user handler. There is
        **no** async runtime in the request path -- the Rust core
        blocks per request on a Python worker, then writes the
        response in one go.

        Trade-offs vs :meth:`run_async`:

        - + Lower per-request latency for pure-CPU handlers
              (no async runtime overhead, no ASGI hop).
        - + Zero Python imports per request.
        - - No streaming responses (SSE, NDJSON, large files).
        - - No HTTP/2, no WebSockets.
        - - ``workers > 1`` is implemented as a ``fork``-based
              process pool, not uvicorns worker supervisor.
        """
        if workers > 1:
            import multiprocessing
            import os

            if not hasattr(os, "fork"):
                raise RuntimeError("Rivex sync workers require fork support on this platform")

            ctx = multiprocessing.get_context("fork")
            processes = [
                ctx.Process(target=self.run_sync, args=(host, port), kwargs={"workers": 1})
                for _ in range(workers)
            ]
            for process in processes:
                process.start()

            try:
                for process in processes:
                    process.join()
            except KeyboardInterrupt:
                pass
            finally:
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                for process in processes:
                    process.join()
            return

        self._run_rust_sync_server(host, port)

    def _run_rust_async_server(self, host: str, port: int) -> None:
        """Inner loop of :meth:`run_async` -- hyper+Tokio engine.

        Drives the Rust ``RivexServer`` (hyper+Tokio) to completion.
        Supports HTTP/1, HTTP/2, streaming responses, and websockets.
        """
        self._drive_rust_server(self._server, host, port, supports_ws=True)

    def _run_rust_sync_server(self, host: str, port: int) -> None:
        """Inner loop of :meth:`run_sync` -- std::thread + httparse engine.

        Drives the Rust ``RivexSyncServer`` (no async runtime, no HTTP/2,
        no streaming). The HTTP API of the helper is the same as
        :meth:`_run_rust_async_server`, just the engine differs.
        """
        self._drive_rust_server(self._sync_server, host, port, supports_ws=False)

    def _install_access_key_middleware_if_needed(self) -> None:
        """Auto-register :class:`AccessKeyMiddleware` when any route declares one.

        Skips registration if:

        * No route has ``access_key`` set.
        * The user already added ``AccessKeyMiddleware`` themselves.
        """
        if not any(getattr(r, "access_key", None) for r in self._routes):
            return
        try:
            from rivex.middleware.access_key import AccessKeyMiddleware
        except ImportError:
            return
        for cls, _ in self._middleware:
            if cls is AccessKeyMiddleware:
                return
        self.add_middleware(AccessKeyMiddleware, routes=list(self._routes))

    def _drive_rust_server(
        self,
        server: Any,
        host: str,
        port: int,
        *,
        supports_ws: bool,
    ) -> None:
        """Shared inner loop for the two Rust engines.

        Registers the user routes, mounts the side routes (CORS preflight,
        OpenAPI, docs, landing, mounted sub-apps), installs the signal
        handler, drives ``server.run(host, port)`` to completion, and
        runs the shutdown hooks / lifespan exit in a ``finally`` block.

        The two engines are exposed as the same Python class (``add_route``,
        ``add_websocket_route``) so the rest of the registration code is
        engine-agnostic.
        """
        lifespan_state = self._enter_lifespan()
        self._run_hooks(self._startup_hooks)

        # Auto-install the access-key middleware if any route declared an
        # ``access_key`` so callers don't have to remember to wire it.
        self._install_access_key_middleware_if_needed()

        hook_mw_cls = self._build_hook_middleware()
        if hook_mw_cls:
            self._middleware.insert(0, (hook_mw_cls, {}))

        _in_flight = 0

        async def _track_before(request_data: dict) -> None:
            """Increment the in-flight request counter used by graceful shutdown.

            Args:
                request_data: The inbound request envelope; not
                    inspected, only present to fit the
                    ``before_request`` hook signature.
            """
            nonlocal _in_flight
            _in_flight += 1

        async def _track_after(request_data: dict, response: dict) -> None:
            """Decrement the in-flight counter once the response has been sent.

            Args:
                request_data: The inbound request envelope; not
                    inspected.
                response: The outbound response envelope; not
                    inspected.
            """
            nonlocal _in_flight
            _in_flight -= 1

        # Guard against re-registration: ``_drive_rust_server`` may
        # be called multiple times if the user calls ``run()``
        # repeatedly on the same app. Without this, the tracking
        # closures pile up and ``_in_flight`` gets double-counted.
        if not getattr(self, "_track_hooks_installed", False):
            self._before_request_hooks.append(_track_before)
            self._after_response_hooks.append(_track_after)
            self._track_hooks_installed = True

        from rivex.middleware.middleware import CORSMiddleware

        has_cors = any(
            isinstance(cls, type) and issubclass(cls, CORSMiddleware) for cls, _ in self._middleware
        )
        registered_paths: set[str] = set()
        # Map path → host constraint so the CORS preflight (OPTIONS)
        # registration below can carry the same host filter; otherwise
        # preflights would respond on every host, leaking the route to
        # untrusted domains.
        path_hosts: dict[str, str | None] = {}

        exc_handlers = self._exception_handlers if self._exception_handlers else None
        dep_overrides = self.dependency_overrides if self.dependency_overrides else None

        for record in self._routes:
            # ── Auto-bake trivial handlers ───────────────────────
            # If the user decorated the handler with
            # ``@cached_response`` (which exposes ``__call_baked__``),
            # we call it once with a sentinel request, capture the
            # response, and register it as a Rust-side const route.
            # Subsequent requests bypass Python entirely -- they hit
            # the same O(1) ``HashMap`` lookup that
            # ``app.add_const_route`` uses. This is the same trick
            # Robyn does in its ``ConstRouter``: turn any handler
            # that returns a constant response into a const route
            # transparently.
            baked: dict | None = None
            try:
                bake_fn = getattr(record.endpoint, "__call_baked__", None)
                if bake_fn is not None:
                    baked = bake_fn()
            except Exception:
                baked = None

            skip_wrapper = getattr(record.endpoint, "_rivex_sse_handler", False)
            jwt_config = getattr(record.endpoint, "_rivex_jwt_config", None)
            if skip_wrapper:
                wrapper_fn = record.endpoint
            else:
                wrapper_fn = build_handler_wrapper(
                    record.endpoint,
                    record.path,
                    record.status_code,
                    self.debug,
                    exc_handlers,
                    record.response_model,
                    dep_overrides,
                    response_model_include=record.response_model_include,
                    response_model_exclude=record.response_model_exclude,
                    response_model_exclude_unset=record.response_model_exclude_unset,
                    response_model_exclude_defaults=record.response_model_exclude_defaults,
                    response_model_exclude_none=record.response_model_exclude_none,
                )
            handler = self._apply_middleware(wrapper_fn)
            if jwt_config:
                from rivex.auth.auth import _build_jwt_wrapper
                handler = _build_jwt_wrapper(handler, jwt_config)
            if record.host:
                try:
                    server.add_route(record.method, record.path, handler, host=record.host)
                except TypeError:
                    server.add_route(record.method, record.path, handler)
                registered_paths.add(record.path)
                path_hosts[record.path] = record.host
                continue
            server.add_route(record.method, record.path, handler)
            registered_paths.add(record.path)
            path_hosts[record.path] = None

            # If the bake succeeded, register the same response as a
            # Rust-side const route too. The Rust listener checks the
            # const cache before the matchit trie, so the second and
            # subsequent requests bypass Python entirely.
            if isinstance(baked, dict):
                try:
                    status_b = int(baked.get("status", 200))
                    body_b = baked.get("body", b"")
                    if isinstance(body_b, str):
                        body_b = body_b.encode("utf-8")
                    elif not isinstance(body_b, (bytes, bytearray)):
                        body_b = b""
                    headers_list = baked.get("headers", []) or []
                    raw_headers: list[tuple[str, str]] = []
                    for h in headers_list:
                        if isinstance(h, tuple) and len(h) == 2:
                            raw_headers.append((str(h[0]), str(h[1])))
                    server.add_const_route(
                        record.method,
                        record.path,
                        status_b,
                        body_b,
                        raw_headers,
                    )
                except Exception:
                    # Const-route registration failed (e.g. path
                    # parameters) -- fall back to the dynamic route.
                    pass

        from rivex.protocols.websockets import WebSocket

        if supports_ws:
            for ws_path, ws_handler in self._ws_routes:

                async def ws_wrapper(raw_ws: Any, _handler: Callable = ws_handler) -> None:
                    """Adapt a raw WebSocket protocol message stream into a Rivex :class:`WebSocket` and dispatch to the user's handler.

                    Always closes the socket in a ``finally`` block
                    so that handler exceptions cannot leak a
                    dangling connection back to the client.

                    Args:
                        raw_ws: The protocol-level WebSocket
                            object provided by the server.
                        _handler: The user's WebSocket handler;
                            captured via default-argument trick so
                            the closure binds the right handler per
                            route.
                    """
                    ws = WebSocket(raw_ws)
                    try:
                        await _handler(ws)
                    finally:
                        await ws.close()

                server.add_websocket_route(ws_path, ws_wrapper)
        elif self._ws_routes:
            import warnings

            warnings.warn(
                f"WebSocket routes {len(self._ws_routes)} registered on the sync server. "
                "The sync engine doesnt support WebSocket upgrades; use `app.run_async()` "
                "to serve them.",
                stacklevel=2,
            )

        _mount_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
        for mount_path, mount_app in self._mounts:
            catch_all = mount_path + "/{path:path}"

            async def _mount_handler(
                request_data: dict,
                *,
                _app: Any = mount_app,
                _prefix: str = mount_path,
            ) -> dict:
                """Strip the mount prefix from the request path and delegate to the sub-application.

                The mount prefix is removed so the sub-app sees
                paths relative to its own root. A ``dict`` copy of
                ``request_data`` is mutated rather than the original
                so the caller's envelope is preserved.

                Args:
                    request_data: The inbound request envelope.
                    _app: The sub-application; captured via default
                        arg so the closure binds the right app per
                        mount.
                    _prefix: The mount path prefix to strip.

                Returns:
                    The raw response envelope produced by the
                    sub-application.
                """
                original = request_data.get("path", "/")
                request_data = dict(request_data)
                request_data["path"] = original[len(_prefix) :] or "/"
                result: dict = await _app(request_data)
                return result

            for method in _mount_methods:
                server.add_route(method, catch_all, _mount_handler)

        if has_cors:

            async def _noop(request_data: dict) -> dict:
                """Return a 204 No Content response for CORS preflight ``OPTIONS`` requests.

                Args:
                    request_data: The inbound request envelope;
                        not inspected.

                Returns:
                    An empty 204 envelope.
                """
                return {"status": 204, "headers": [], "body": b""}

            for path in registered_paths:
                handler = self._apply_middleware(_noop)
                # NB: use a distinct name -- reusing ``host`` here would clobber
                # the server *bind address* parameter of this method, so a CORS
                # app would later call ``server.run(None, port)`` and crash.
                route_host = path_hosts.get(path)
                if route_host:
                    try:
                        server.add_route("OPTIONS", path, handler, host=route_host)
                    except TypeError:
                        server.add_route("OPTIONS", path, handler)
                else:
                    server.add_route("OPTIONS", path, handler)

        if self.openapi_url:
            self._register_openapi_routes(server, registered_paths)
            registered_paths.update(
                p
                for p in (
                    self.openapi_url,
                    self.docs_url,
                    self.redoc_url,
                    self.health_url,
                )
                if p
            )

        if self.asyncapi_url and self._ws_routes:
            self._register_asyncapi_route(server, registered_paths)

        if self.landing_page:
            self._register_landing_route(server, registered_paths)

        _shutting_down = False

        def _signal_handler(signum, frame):
            """Top-level SIGTERM/SIGINT handler that initiates graceful shutdown.

            Idempotent — a second signal during shutdown is
            ignored. Spawns a daemon thread that runs
            :func:`_graceful_stop`, which drains in-flight
            requests and sleeps for the configured timeout.
            """
            nonlocal _shutting_down
            if _shutting_down:
                return
            _shutting_down = True
            import threading
            import time

            drain = self.drain_timeout

            def _graceful_stop():
                """Wait for in-flight requests to drain, then sleep out the shutdown timeout.

                Loops at ``0.1s`` intervals while the in-flight
                counter is positive and the drain window has not
                elapsed, then sleeps whatever remains of
                ``self.shutdown_timeout`` so the Rust core has time
                to flush accepted sockets.
                """
                nonlocal _in_flight
                start = time.monotonic()
                while _in_flight > 0 and (time.monotonic() - start) < drain:
                    time.sleep(0.1)
                time.sleep(max(0, self.shutdown_timeout - (time.monotonic() - start)))

            stopper = threading.Thread(target=_graceful_stop, daemon=True)
            stopper.start()

        prev_sigterm = signal.getsignal(signal.SIGTERM)
        prev_sigint = signal.getsignal(signal.SIGINT)
        try:
            signal.signal(signal.SIGTERM, _signal_handler)
            signal.signal(signal.SIGINT, _signal_handler)
        except ValueError:
            # Tests may call run() from a background thread.
            prev_sigterm = None
            prev_sigint = None

        try:
            # Apply Tier 1 security config (CORS / CSRF / HSTS /
            # trusted hosts / XSS / body limit) to BOTH engines so
            # the same protections apply whether the user calls
            # ``run()``, ``run_async()`` or ``run_sync()``.
            if self._security_config is not None:
                self._server.set_security(self._security_config)
                self._sync_server.set_security(self._security_config)
            server.run(host, port)
        except KeyboardInterrupt:
            pass
        finally:
            if prev_sigterm is not None:
                signal.signal(signal.SIGTERM, prev_sigterm)
            if prev_sigint is not None:
                signal.signal(signal.SIGINT, prev_sigint)
            self._run_hooks(self._shutdown_hooks)
            self._exit_lifespan(lifespan_state)

    # ── internal helpers ──

    def _mount_admin(self, base_path: str, token: str | None) -> None:
        """Mount the admin dashboard at *base_path* with optional *token* auth.

        Discovery: first, try the entry-point group
        ``rivex.plugins.admin``.  If at least one plugin is registered
        there, mount them in order.  If none are registered, fall
        back to the built-in ``rivex_admin`` companion package
        (installed via ``pip install rivex[admin]``).  If neither
        is available, raise a clear error.

        Authentication: prefer the SQLite user store at
        ``self.admin_db`` (default ``./.rivex/admin.db``); fall
        back to the legacy single ``admin_token`` if no users exist
        in the DB.
        """
        from rivex.cli.plugins import load_plugins

        admin_plugins = load_plugins("rivex.plugins.admin")
        if admin_plugins:
            # The first registered admin plugin wins.  Users can ship
            # their own admin by registering a single entry point.
            _, register = next(iter(admin_plugins.items()))
            register(
                self,
                base_path=base_path,
                token=token,
                admin_db=self.admin_db,
            )
            return

        try:
            from rivex_admin import register_admin_routes
        except ImportError as exc:
            raise RuntimeError(
                "The admin dashboard requires the optional `rivex_admin` "
                "package. Install it with: pip install rivex[admin]"
            ) from exc
        # Store the admin_db on the app so the dashboard can show
        # the path on the "no admin configured" partial.
        self._admin_db = self.admin_db
        register_admin_routes(
            self,
            base_path=base_path,
            token=token,
            admin_db=self.admin_db,
        )

    def _register_landing_route(self, server: Any, registered_paths: set[str]) -> None:
        """Mount a bare-bones HTML landing page at ``GET /`` if no user
        route owns that path yet.

        Pure-Python path: no Rust core dependency, so it works in
        bare-bones installs.  Real applications shadow it by defining
        their own ``@app.get("/")`` route.

        ``server`` is the active Rust engine (``RivexServer`` or
        ``RivexSyncServer``); the registration API is the same.
        """
        if "/" in registered_paths:
            return
        from rivex.web._landing import build_landing_page

        app = self

        async def _landing(request_data: dict[str, Any]) -> dict[str, Any]:
            """Serve the bundled HTML landing page for ``GET /``.

            Args:
                request_data: The inbound request envelope;
                    not inspected.

            Returns:
                A 200 response envelope carrying the landing
                page HTML and the appropriate ``Content-Type``.
            """
            body, content_type = build_landing_page(app)
            return {
                "status": 200,
                "headers": [("content-type", content_type)],
                "body": body.encode("utf-8"),
            }

        handler = self._apply_middleware(_landing)
        server.add_route("GET", "/", handler)

    def _register_openapi_routes(
        self, server: Any, registered_paths: set[str] | None = None
    ) -> None:
        """Attach the OpenAPI / Swagger UI / ReDoc / health routes to *server*.

        Generates the OpenAPI spec from the registered routes
        once, pre-renders the Swagger UI, ReDoc, and health HTML
        pages, and registers the OpenAPI JSON endpoint plus the
        three documentation/health endpoints on *server*. Already
        registered paths are skipped so user routes shadowing any
        of these URLs are preserved.

        Args:
            server: The active Rust engine. Accepts both
                ``RivexServer`` and ``RivexSyncServer``.
            registered_paths: Optional set tracking every path
                this method has registered so the surrounding
                loop can avoid double-registering paths.
        """
        from rivex.openapi.openapi import (
            build_docs_html,
            build_health_html,
            build_redoc_html,
            generate_openapi,
        )

        spec = generate_openapi(
            title=self.title,
            version=self.version,
            description=self.description,
            routes=self._routes,
            openapi_tags=self.openapi_tags,
            servers=self.servers,
            terms_of_service=self.terms_of_service,
            contact=self.contact,
            license_info=self.license_info,
        )
        spec_bytes = json.dumps(spec, indent=2).encode("utf-8")

        async def openapi_handler(request_data: dict) -> dict:
            """Return the cached OpenAPI spec JSON for ``GET <openapi_url>``.

            The spec bytes are computed once at registration and the
            handler returns them verbatim, so every request avoids
            re-serialising the entire OpenAPI document.

            Args:
                request_data: The inbound request envelope;
                    not inspected.

            Returns:
                A 200 JSON envelope carrying the pre-serialised
                OpenAPI document.
            """
            return {
                "status": 200,
                "headers": [("content-type", "application/json")],
                "body": spec_bytes,
            }

        assert self.openapi_url is not None
        try:
            server.add_route("GET", self.openapi_url, openapi_handler)
        except ValueError:
            pass
        if registered_paths is not None and self.openapi_url:
            registered_paths.add(self.openapi_url)

        if self.docs_url:
            assert self.openapi_url is not None
            html_bytes = build_docs_html(
                self.title,
                self.openapi_url,
                logo_url=self.logo_url,
                description=self.description,
                favicon_url=self.favicon_url,
                app_name=self.app_name,
                powered_by=self.powered_by,
            ).encode("utf-8")

            async def docs_handler(request_data: dict) -> dict:
                """Serve the pre-rendered Swagger UI HTML page at ``GET <docs_url>``.

                Args:
                    request_data: The inbound request envelope;
                        not inspected.

                Returns:
                    A 200 HTML envelope carrying the Swagger UI
                document.
                """
                return {
                    "status": 200,
                    "headers": [("content-type", "text/html; charset=utf-8")],
                    "body": html_bytes,
                }

            try:
                server.add_route("GET", self.docs_url, docs_handler)
            except ValueError:
                pass
            if registered_paths is not None and self.docs_url:
                registered_paths.add(self.docs_url)

        if self.redoc_url:
            assert self.openapi_url is not None
            redoc_bytes = build_redoc_html(
                self.title,
                self.openapi_url,
                favicon_url=self.favicon_url,
                app_name=self.app_name,
                powered_by=self.powered_by,
            ).encode("utf-8")

            async def redoc_handler(request_data: dict) -> dict:
                """Serve the pre-rendered ReDoc HTML page at ``GET <redoc_url>``.

                Args:
                    request_data: The inbound request envelope;
                        not inspected.

                Returns:
                    A 200 HTML envelope carrying the ReDoc
                document.
                """
                return {
                    "status": 200,
                    "headers": [("content-type", "text/html; charset=utf-8")],
                    "body": redoc_bytes,
                }

            server.add_route("GET", self.redoc_url, redoc_handler)
            if registered_paths is not None and self.redoc_url:
                registered_paths.add(self.redoc_url)

        if self.health_url and self.health_url not in (registered_paths or ()):
            health_bytes = build_health_html(
                self.title,
                self.version,
                docs_url=self.docs_url,
                favicon_url=self.favicon_url,
                app_name=self.app_name,
                powered_by=self.powered_by,
            ).encode("utf-8")

            async def health_handler(request_data: dict) -> dict:
                """Serve the pre-rendered health/dashboard HTML at ``GET <health_url>``.

                Args:
                    request_data: The inbound request envelope;
                        not inspected.

                Returns:
                    A 200 HTML envelope carrying the health
                page.
                """
                return {
                    "status": 200,
                    "headers": [("content-type", "text/html; charset=utf-8")],
                    "body": health_bytes,
                }

            server.add_route("GET", self.health_url, health_handler)
            if registered_paths is not None and self.health_url:
                registered_paths.add(self.health_url)

        liveness_bytes = b"{\"status\":\"healthy\"}"
        def _make_k8s_handler(body: bytes, status: int = 200):
            """Build a request handler that returns a fixed JSON body and status.

            Used for the liveness/readiness probes: both routes
            return the same payload, just possibly with different
            status codes.

            Args:
                body: The response body bytes.
                status: The HTTP status code to return.

            Returns:
                An async function suitable for use as a server
                route handler.
            """
            async def _handler(request_data: dict) -> dict:
                """Return the configured ``(status, body)`` envelope for a Kubernetes probe."""
                return {
                    "status": status,
                    "headers": [("content-type", "application/json")],
                    "body": body,
                }
            return _handler

        if self.liveness_url:
            server.add_route("GET", self.liveness_url, _make_k8s_handler(liveness_bytes))
            if registered_paths is not None and self.liveness_url:
                registered_paths.add(self.liveness_url)

        if self.readiness_url:
            server.add_route("GET", self.readiness_url, _make_k8s_handler(liveness_bytes))
            if registered_paths is not None and self.readiness_url:
                registered_paths.add(self.readiness_url)

    # ── templating ──

    def template(
        self,
        name: str,
        context: dict[str, Any] | None = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Render a Jinja2 template and return a dict response.

        The first call lazily creates a ``Jinja2Templates`` instance
        using ``self.template_dir`` (default ``"templates/"``).

        Usage::

            @app.get("/page")
            async def page(request):
                return app.template("page.html", {"title": "Hello"})
        """
        from rivex.web.templating import Jinja2Templates

        if self._templates is None:
            dir = self.template_dir or "templates/"
            self._templates = Jinja2Templates(dir)
        resp = self._templates.render(name, **(context or {}))
        if status_code != 200:
            resp.status_code = status_code
        if headers:
            resp.headers.update(headers)
        return resp._to_raw()

    # ── dependency overrides (testing helpers) ──

    def override_dependency(
        self, original: Callable, mock: Callable
    ) -> None:
        """Replace *original* with *mock* in test overrides.

        ``clear_overrides()`` restores all originals.
        """
        self.dependency_overrides[original] = mock

    def clear_overrides(self) -> None:
        """Remove all dependency overrides."""
        self.dependency_overrides.clear()

    @contextmanager
    def override_scope(
        self, overrides: dict[Callable, Callable]
    ) -> Iterator[None]:
        """Temporarily replace dependencies within a ``with`` block.

        Example::

            with app.override_scope({get_db: mock_db}):
                resp = client.get("/items")
        """
        saved = dict(self.dependency_overrides)
        self.dependency_overrides.update(overrides)
        try:
            yield
        finally:
            self.dependency_overrides.clear()
            self.dependency_overrides.update(saved)

    def _register_asyncapi_route(
        self, server: Any, registered_paths: set[str] | None = None
    ) -> None:
        """Attach the AsyncAPI JSON and viewer-HTML routes to *server*.

        Generates the AsyncAPI spec from the app's WebSocket
        routes once and registers two endpoints: the JSON spec at
        :attr:`asyncapi_url` and the HTML viewer at
        :attr:`asyncapi_docs_url`. The latter is only registered
        when the URL is configured.

        Args:
            server: The active Rust engine.
            registered_paths: Optional set tracking every path
                this method has registered so the surrounding
                loop can avoid double-registering paths.
        """
        from rivex.openapi.asyncapi import build_asyncapi_html, generate_asyncapi

        spec = generate_asyncapi(
            title=self.title,
            version=self.version,
            description=self.description,
            ws_routes=self._ws_routes,
            servers=self.servers,
        )
        spec_bytes = json.dumps(spec, indent=2).encode("utf-8")

        async def asyncapi_handler(request_data: dict) -> dict:
            """Return the cached AsyncAPI spec JSON for ``GET <asyncapi_url>``.

            Args:
                request_data: The inbound request envelope;
                    not inspected.

            Returns:
                A 200 JSON envelope carrying the pre-serialised
                AsyncAPI document.
            """
            return {
                "status": 200,
                "headers": [("content-type", "application/json")],
                "body": spec_bytes,
            }

        assert self.asyncapi_url is not None
        server.add_route("GET", self.asyncapi_url, asyncapi_handler)
        if registered_paths is not None and self.asyncapi_url:
            registered_paths.add(self.asyncapi_url)

        if self.asyncapi_docs_url:
            html_bytes = build_asyncapi_html(
                self.asyncapi_url,
                title=f"{self.title} -- AsyncAPI",
            ).encode("utf-8")

            async def asyncapi_docs_handler(request_data: dict) -> dict:
                """Serve the pre-rendered AsyncAPI HTML viewer at ``GET <asyncapi_docs_url>``.

                Args:
                    request_data: The inbound request envelope;
                        not inspected.

                Returns:
                    A 200 HTML envelope carrying the AsyncAPI
                    viewer page.
                """
                return {
                    "status": 200,
                    "headers": [("content-type", "text/html; charset=utf-8")],
                    "body": html_bytes,
                }

            server.add_route("GET", self.asyncapi_docs_url, asyncapi_docs_handler)
            if registered_paths is not None and self.asyncapi_docs_url:
                registered_paths.add(self.asyncapi_docs_url)

    def _build_hook_middleware(self) -> type | None:
        """Create a middleware class that runs lifecycle hooks."""
        if not (
            self._before_request_hooks or self._after_request_hooks or self._after_response_hooks
        ):
            return None

        return _make_hook_middleware(
            self._before_request_hooks,
            self._after_request_hooks,
            self._after_response_hooks,
        )

    def _apply_middleware(self, handler: Callable) -> Callable:
        """Wrap *handler* with the app's full middleware chain.

        Delegates to :func:`rivex.middleware._mw_utils.apply_middleware_chain`
        so the middleware ordering and error handling are shared
        across the framework.

        Args:
            handler: The innermost handler the chain should
                ultimately invoke.

        Returns:
            The wrapped callable that, when called, runs the
            entire middleware chain.
        """
        from rivex.middleware._mw_utils import apply_middleware_chain

        return apply_middleware_chain(handler, self._middleware)

    def _run_hooks(self, hooks: list[Callable]) -> None:
        """Invoke each hook in *hooks*, driving coroutines synchronously.

        Async hooks are run via :func:`_run_coroutine_sync`; sync
        hooks are called directly.

        Args:
            hooks: List of zero-argument lifecycle callables.
                Coroutine functions are awaited, plain functions
                are called.
        """
        for hook in hooks:
            if asyncio.iscoroutinefunction(hook):
                _run_coroutine_sync(hook())
            else:
                hook()

    @staticmethod
    def _run_async(coro: Any) -> None:
        """Synchronously drive *coro* to completion.

        Thin wrapper around :func:`_run_coroutine_sync` so the
        framework can call :meth:`_run_async` from synchronous
        lifecycle hooks without losing readability.

        Args:
            coro: An awaitable coroutine to run to completion.
        """
        _run_coroutine_sync(coro)

    def _enter_lifespan(self) -> Any:
        """Activate the user-supplied lifespan context manager and connect DB pools.

        Idempotent — a second call while the lifespan is active
        returns the cached state without re-running user code.
        Sync (``__enter__``) and async (``__aenter__``) context
        managers are both supported and the mode is recorded so
        :meth:`_exit_lifespan` knows which exit method to call.

        Returns:
            ``None`` when no lifespan is configured, otherwise an
            opaque state token suitable for :meth:`_exit_lifespan`.

        Raises:
            TypeError: When ``self.lifespan`` returns something
                that is neither a sync nor an async context
                manager.
        """
        # Guard against re-entry: if the lifespan is already active,
        # return the current state without trying to re-connect DB
        # pools or re-enter the users context manager.
        if getattr(self, "_lifespan_state", None) is not None:
            return self._lifespan_state
        # Auto-connect database pools (skip if already connected).
        if self._db._configs and not getattr(self._db, "_connected", False):
            _run_coroutine_sync(self._db.connect_all())

        if self.lifespan is None:
            return None

        context = self.lifespan(self)
        enter = getattr(context, "__enter__", None)
        if callable(enter):
            enter()
            self._lifespan_state = ("sync", context)
            return self._lifespan_state

        async_enter = getattr(context, "__aenter__", None)
        if callable(async_enter):
            _run_coroutine_sync(async_enter())
            self._lifespan_state = ("async", context)
            return self._lifespan_state

        raise TypeError("lifespan must return a context manager")

    def _exit_lifespan(self, state: Any) -> None:
        """Exit the lifespan previously entered via :meth:`_enter_lifespan`.

        Disconnects database pools first, then dispatches to the
        appropriate ``__exit__`` / ``__aexit__`` based on the mode
        captured at entry. ``state=None`` is the no-op path
        returned when no lifespan was configured.

        Args:
            state: The opaque state returned by
                :meth:`_enter_lifespan`.
        """
        # Reset the re-entry guard so a future ``_enter_lifespan``
        # starts fresh.
        self._lifespan_state = None
        # Auto-disconnect database pools
        if self._db._connected:
            _run_coroutine_sync(self._db.disconnect_all())

        if state is None:
            return

        mode, context = state
        if mode == "sync":
            context.__exit__(None, None, None)
        else:
            _run_coroutine_sync(context.__aexit__(None, None, None))

    # ── ASGI interface ──

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        if not hasattr(self, "_asgi_adapter"):
            from rivex.native.asgi import ASGIAdapter

            self._asgi_adapter = ASGIAdapter(self)
        await self._asgi_adapter(scope, receive, send)


FastAPI = Rivex

# Used by the multi-process supervisor in ``_run_async_multi_process``.
# Previously aliased to ``Rivex`` here at module level (after the
# class body) so isinstance checks inside the class could reference
# it. That was fragile (worked only because of Pythons late name
# resolution). The isinstance sites now reference ``Rivex`` directly
# -- the class is in scope at call time, so this is safe and removes
# the order-of-evaluation hazard.
