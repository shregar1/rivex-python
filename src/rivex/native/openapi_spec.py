"""OpenAPI spec endpoint via Rust const routes.

Serialises the OpenAPI spec to JSON once at registration time and
registers it as a Rust const route. Every subsequent request for the
spec gets the same pre-baked bytes from the Rust HashMap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rivex.applications.applications import Rivex


def openapi(
    app: Rivex,
    path: str = "/openapi.json",
    spec: dict | None = None,
    *,
    content_type: str = "application/json",
    cache_control: str | None = "public, max-age=3600",
) -> None:
    """Register an OpenAPI spec endpoint as a Rust const route.

    Args:
        app: Rivex application instance.
        path: URL path (default ``"/openapi.json"``).
        spec: OpenAPI spec dict. If ``None``, calls ``app.openapi()``
            to generate the spec from registered routes.
        content_type: ``Content-Type`` header value.
        cache_control: ``Cache-Control`` header value. Default is
            one hour since the spec doesn't change between deploys.

    Raises:
        ValueError: If the app has no OpenAPI spec and ``spec`` is None.
    """
    if spec is None:
        # Try to get the spec from the app
        spec_generator = getattr(app, "openapi", None)
        if spec_generator is None:
            raise ValueError(
                "App has no openapi() method and no spec was provided. "
                "Pass spec=<dict> explicitly."
            )
        spec = spec_generator()

    if not isinstance(spec, dict):
        raise TypeError(f"OpenAPI spec must be a dict, got {type(spec).__name__}")

    # Serialise to JSON bytes via Rust core
    from rivex.serialization import _json

    body_bytes = _json.dumps(spec)

    # Build headers
    headers: list[tuple[str, str]] = [("content-type", content_type)]
    if cache_control:
        headers.append(("cache-control", cache_control))

    # Register as a Rust const route
    app.add_const_route("GET", path, 200, body_bytes, headers)
