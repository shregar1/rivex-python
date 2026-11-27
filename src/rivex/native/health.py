"""Health/liveness check endpoint via Rust const routes.

Registers a fixed ``200 OK`` response at ``/health`` (or any path) as a
Rust const route. The response is served from the Rust HashMap at
sub-microsecond latency — ideal for Kubernetes liveness/readiness probes
that fire every few seconds.

For readiness checks that depend on external state (DB, cache, message
queue), use a regular Python handler instead — the native health check
is only for ``is this process alive?`` semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rivex.applications.applications import Rivex


def health(
    app: Rivex,
    path: str = "/health",
    *,
    status: int = 200,
    body: dict | str | bytes | None = None,
    content_type: str = "application/json",
    cache_control: str | None = "no-cache",
) -> None:
    """Register a health check endpoint as a Rust const route.

    Args:
        app: Rivex application instance.
        path: URL path (default ``"/health"``).
        status: HTTP status code (default ``200``).
        body: Response body. ``dict`` is JSON-serialised via
            :func:`rivex_core.json_serialize`; ``str`` is UTF-8 encoded;
            ``bytes`` is used as-is. Default ``{"status": "ok"}``.
        content_type: ``Content-Type`` header value.
        cache_control: ``Cache-Control`` header value (default
            ``"no-cache"`` so probes don't get cached).

    Raises:
        TypeError: If ``body`` is a type that cannot be serialised.
    """
    # Resolve the body to bytes
    if body is None:
        body = {"status": "ok"}

    if isinstance(body, bytes):
        body_bytes = body
    elif isinstance(body, str):
        body_bytes = body.encode("utf-8")
    elif isinstance(body, dict):
        from rivex.serialization import _json

        body_bytes = _json.dumps(body)
    else:
        # Try JSON serialisation for other types (list, int, etc.)
        from rivex.serialization import _json

        body_bytes = _json.dumps(body)

    # Build headers
    headers: list[tuple[str, str]] = [("content-type", content_type)]
    if cache_control:
        headers.append(("cache-control", cache_control))

    # Register as a Rust const route — served from HashMap at request time
    app.add_const_route("GET", path, status, body_bytes, headers)
