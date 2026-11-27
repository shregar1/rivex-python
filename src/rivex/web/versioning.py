"""``rivex.web.versioning`` — URL-based API versioning helpers.

Provides :class:`VersionedRouter` which wraps a :class:`rivex.Rivex` (or any
compatible app) to prefix routes with a version segment such as ``/v1``.
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = ["VersionedRouter"]


class VersionedRouter:
    """Register routes on *app* under a versioned path prefix.

    Example::

        v1 = VersionedRouter(app, version=1, prefix="/api")

        @v1.get("/users")
        def list_users():
            return []

    This registers the route at ``/api/v1/users``.

    Parameters
    ----------
    app:
        The parent application (must expose a ``route`` registration method).
    version:
        Integer version number (e.g. ``1`` → ``/v1``).
    prefix:
        Optional path prefix prepended before the version segment.
        Defaults to ``""`` (no prefix beyond ``/v{version}``).
    """

    def __init__(self, app: Any, *, version: int, prefix: str = "") -> None:
        self._app = app
        self._version = version
        self._prefix = prefix.rstrip("/")
        self._version_prefix = f"{self._prefix}/v{version}"

    # ── HTTP method shortcuts ─────────────────────────────────────────────────

    def get(self, path: str, **kwargs: Any) -> Callable:
        return self._register("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable:
        return self._register("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Callable:
        return self._register("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Callable:
        return self._register("DELETE", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Callable:
        return self._register("PATCH", path, **kwargs)

    def options(self, path: str, **kwargs: Any) -> Callable:
        return self._register("OPTIONS", path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> Callable:
        return self._register("HEAD", path, **kwargs)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _register(self, method: str, path: str, **kwargs: Any) -> Callable:
        full_path = self._version_prefix + path
        method_lower = method.lower()

        def decorator(handler: Callable) -> Callable:
            # Prefer method-specific decorator (e.g. app.get, app.post) which
            # is the standard Rivex API.  Fall back to generic .route() or
            # .add_route() for other ASGI-compatible apps.
            if hasattr(self._app, method_lower):
                getattr(self._app, method_lower)(full_path, **kwargs)(handler)
            elif hasattr(self._app, "route"):
                self._app.route(method, full_path, **kwargs)(handler)
            elif hasattr(self._app, "add_route"):
                self._app.add_route(full_path, handler, methods=[method], **kwargs)
            else:
                raise AttributeError(
                    f"{type(self._app).__name__!r} has no method-specific decorator, "
                    f"'route', or 'add_route' method."
                )
            return handler

        return decorator
