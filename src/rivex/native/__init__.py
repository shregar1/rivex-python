"""Rivex native handlers — Rust-speed responses for common patterns.

Native handlers pre-compute responses at startup and register them as
Rust-side const routes. At request time, the Rust core serves them from
an O(1) HashMap lookup — Python is never invoked.

Patterns supported:
    - Static file serving (directory walk → const routes)
    - Health/liveness checks
    - OpenAPI spec endpoint
    - Redirects/rewrites

Usage::

    from rivex import Rivex
    from rivex.native import NativeHandlers

    app = Rivex()

    NativeHandlers.serve_static(app, "/static", "./public")
    NativeHandlers.health(app, "/health")
    NativeHandlers.openapi(app, "/openapi.json", spec)
    NativeHandlers.redirect(app, "/old", "/new", permanent=True)

Performance:
    Native handlers match ``const=True`` throughput (~500K+ RPS) because
    they use the same Rust HashMap lookup mechanism. The difference is
    ergonomics: native handlers handle the registration boilerplate
    (file walking, MIME detection, ETag generation, path traversal
    protection) for you.

See :mod:`rivex.native.static_files`, :mod:`rivex.native.health`,
:mod:`rivex.native.openapi_spec`, :mod:`rivex.native.redirects` for
per-pattern details.
"""

from __future__ import annotations

from rivex.native.health import health
from rivex.native.openapi_spec import openapi
from rivex.native.raw import raw_html, raw_json, raw_response, raw_text
from rivex.native.redirects import redirect
from rivex.native.static_files import serve_static

__all__ = [
    "NativeHandlers",
    "health",
    "openapi",
    "raw_html",
    "raw_json",
    "raw_response",
    "raw_text",
    "redirect",
    "serve_static",
]


class NativeHandlers:
    """Namespace for native handler registration methods.

    Each method is a classmethod that registers pre-baked responses
    on a :class:`~rivex.Rivex` app. All methods can also be imported
    individually from :mod:`rivex.native`::

        from rivex.native import serve_static, health, redirect, openapi
    """

    @staticmethod
    def serve_static(
        app,
        route: str = "/static",
        directory: str = ".",
        *,
        index_file: str | None = "index.html",
        cache_control: str | None = None,
        exclude: list[str] | None = None,
        max_file_size: int = 10 * 1024 * 1024,
    ) -> int:
        """Serve a directory of static files as Rust const routes.

        Walks ``directory`` at startup, reads each file, detects its
        MIME type, and registers ``GET {route}/{relative_path}`` as a
        const route. At request time the Rust core serves the file
        bytes from its HashMap — no disk I/O, no Python.

        Args:
            app: A :class:`~rivex.Rivex` application.
            route: URL prefix (default ``"/static"``).
            directory: Filesystem path to serve from.
            index_file: File to serve when the URL ends in ``/``
                (default ``"index.html"``). Pass ``None`` to disable.
            cache_control: Value for the ``Cache-Control`` response
                header (e.g. ``"public, max-age=31536000"``).
            exclude: Glob patterns to exclude (e.g. ``["*.tmp"]``).
            max_file_size: Skip files larger than this (default 10 MB).

        Returns:
            Number of files registered as const routes.
        """
        return serve_static(
            app,
            route=route,
            directory=directory,
            index_file=index_file,
            cache_control=cache_control,
            exclude=exclude,
            max_file_size=max_file_size,
        )

    @staticmethod
    def health(
        app,
        path: str = "/health",
        *,
        status: int = 200,
        body: dict | str | bytes | None = None,
        content_type: str = "application/json",
        cache_control: str | None = "no-cache",
    ) -> None:
        """Register a health/liveness check endpoint.

        Serves a fixed response body at ``path`` as a Rust const route.
        For liveness probes this is a constant ``200 OK`` — sub-microsecond
        response time, no Python involvement.

        Args:
            app: A :class:`~rivex.Rivex` application.
            path: URL path (default ``"/health"``).
            status: HTTP status code (default ``200``).
            body: Response body. ``dict`` is JSON-serialised;
                ``str``/``bytes`` used as-is. Default ``{"status": "ok"}``.
            content_type: ``Content-Type`` header.
            cache_control: ``Cache-Control`` header (default ``"no-cache"``
                so probes don't get cached by intermediaries).
        """
        health(
            app,
            path=path,
            status=status,
            body=body,
            content_type=content_type,
            cache_control=cache_control,
        )

    @staticmethod
    def openapi(
        app,
        path: str = "/openapi.json",
        spec: dict | None = None,
        *,
        content_type: str = "application/json",
        cache_control: str | None = "public, max-age=3600",
    ) -> None:
        """Serve an OpenAPI specification as a pre-baked const route.

        The spec is serialised to JSON once at registration time; every
        subsequent request gets the same bytes from the Rust HashMap.

        Args:
            app: A :class:`~rivex.Rivex` application.
            path: URL path (default ``"/openapi.json"``).
            spec: OpenAPI spec dict. If ``None``, uses ``app.openapi()``.
            content_type: ``Content-Type`` header.
            cache_control: ``Cache-Control`` header.
        """
        openapi(app, path=path, spec=spec, content_type=content_type, cache_control=cache_control)

    @staticmethod
    def redirect(
        app,
        from_path: str,
        to_path: str,
        *,
        permanent: bool = True,
        method: str = "GET",
    ) -> None:
        """Register a redirect as a pre-baked const route.

        Args:
            app: A :class:`~rivex.Rivex` application.
            from_path: URL path to redirect from.
            to_path: Destination URL.
            permanent: ``True`` for 301, ``False`` for 302.
            method: HTTP method to match (default ``"GET"``).
        """
        redirect(app, from_path, to_path, permanent=permanent, method=method)
