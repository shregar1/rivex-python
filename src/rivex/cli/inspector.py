"""``rivex.cli.inspector`` — runtime application inspector.

Provides :class:`Inspector` which mounts diagnostic API endpoints on the
application for live introspection of routes, status, and custom commands.
"""

from __future__ import annotations

import secrets
import sys
from typing import Any, Callable

__all__ = ["Inspector"]


class Inspector:
    """Mount inspector routes on *app* and expose runtime diagnostics.

    Parameters
    ----------
    app:
        The parent Rivex application.
    token:
        Bearer token required to access inspector endpoints.  If omitted a
        secure random token is generated and printed to *stderr*.
    url:
        Base URL prefix for inspector routes. Defaults to ``"/_inspector"``.
    """

    def __init__(
        self,
        app: Any,
        *,
        token: str | None = None,
        url: str = "/_inspector",
    ) -> None:
        self._app = app
        self.url = url.rstrip("/")
        self._commands: dict[str, Callable] = {}

        if token is None:
            token = secrets.token_urlsafe(32)
            print(f"Inspector token: {token}", file=sys.stderr)
        self.token = token

        self._register_routes()

    # ── Route registration ────────────────────────────────────────────────────

    def _register_routes(self) -> None:
        """Attach the inspector's diagnostic endpoints to the parent app.

        Registers ``status``, ``routes``, and ``commands`` endpoints
        under :attr:`inspector.url`. The route registration style is
        auto-detected against the host framework — whichever of
        ``app.get``, ``app.route``, or ``app.add_route`` exists is
        used; otherwise nothing is registered and the inspector is a
        no-op.
        """
        base = self.url

        def _make_handler(name: str):
            """Build a route handler that authenticates then dispatches to ``_handle``."""

            def handler(request: Any = None):
                """Authenticate the request and dispatch it to ``_handle``.

                Wraps each generated route closure so the per-route
                boilerplate (auth check + delegation) lives in one
                place. Authentication is performed first; only valid
                bearer tokens reach the dispatcher.

                Args:
                    request: The inbound request envelope as carried
                        by the host framework. ``None`` is accepted
                        for call sites that do not pass a request.

                Returns:
                    A ``(body, status)`` tuple where ``body`` is the
                    diagnostic payload (or an ``"Unauthorized"``
                    error) and ``status`` is the HTTP status code.
                """
                if not self._check_auth(request or {}):
                    return {"error": "Unauthorized"}, 401
                return self._handle(name, request)

            handler.__name__ = f"_inspector_{name}"
            return handler

        for endpoint in ("status", "routes", "commands"):
            path = f"{base}/{endpoint}"
            if hasattr(self._app, "get"):
                self._app.get(path)(_make_handler(endpoint))
            elif hasattr(self._app, "route"):
                self._app.route("GET", path)(_make_handler(endpoint))
            elif hasattr(self._app, "add_route"):
                self._app.add_route(path, _make_handler(endpoint), methods=["GET"])

    def _handle(self, name: str, request: Any) -> Any:
        """Produce the response body for the ``name`` diagnostic endpoint.

        ``status`` reports a static health payload, ``routes``
        enumerates paths from ``self._app._routes`` if the host app
        exposes one, and ``commands`` returns the keys of any
        user-registered custom commands.

        Args:
            name: One of ``"status"``, ``"routes"``, or
                ``"commands"`` selecting which diagnostic to produce.
            request: The inbound request object; currently unused
                beyond the auth check performed by the caller.

        Returns:
            A JSON-serialisable payload describing the selected
            endpoint's data. An ``"error"`` key is returned when
            ``name`` does not match any known endpoint.
        """
        if name == "status":
            return {"status": "ok"}
        if name == "routes":
            routes = getattr(self._app, "_routes", [])
            return {"routes": [getattr(r, "path", str(r)) for r in routes]}
        if name == "commands":
            return {"commands": list(self._commands.keys())}
        return {"error": "unknown endpoint"}

    # ── Command registration ──────────────────────────────────────────────────

    def command(self, name: str) -> Callable:
        """Decorator that registers a custom inspector command."""

        def decorator(fn: Callable) -> Callable:
            """Register ``fn`` as a custom command named ``name`` and return it unchanged."""

            self._commands[name] = fn
            return fn

        return decorator

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _check_auth(self, request: Any) -> bool:
        """Return ``True`` if *request* carries a valid bearer token."""
        headers: list[tuple[str, str]] = []
        if isinstance(request, dict):
            headers = request.get("headers", [])
        elif hasattr(request, "headers"):
            headers = list(request.headers.items())

        for key, value in headers:
            if key.lower() == "authorization":
                parts = value.split(" ", 1)
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    return parts[1] == self.token
        return False
