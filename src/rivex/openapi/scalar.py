"""Scalar API Reference UI — modern, fast OpenAPI documentation.

Scalar is a modern alternative to Swagger UI and ReDoc with better
performance, dark mode, and search. It loads entirely client-side
from CDN — no server-side rendering required.

Usage::

    from rivex.openapi.scalar import mount_scalar

    # Mount Scalar at /scalar (reads spec from /openapi.json)
    mount_scalar(app, path="/scalar", spec_url="/openapi.json")

    # Or render the HTML directly
    html = render_scalar_html(spec_url="/openapi.json", title="My API")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rivex.applications.applications import Rivex


def render_scalar_html(
    spec_url: str = "/openapi.json",
    *,
    title: str = "API Reference",
    dark_mode: bool = True,
) -> str:
    """Render the Scalar API reference HTML page.

    Args:
        spec_url: URL of the OpenAPI JSON spec.
        title: Page title.
        dark_mode: Use dark theme (default ``True``).

    Returns:
        Complete HTML page as a string.
    """
    theme = "dark" if dark_mode else "light"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
        body {{ margin: 0; }}
    </style>
</head>
<body>
    <script
        id="api-reference"
        data-url="{spec_url}"
        data-theme="{theme}"
    ></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>"""


def mount_scalar(
    app: Rivex,
    path: str = "/scalar",
    *,
    spec_url: str | None = None,
    title: str = "API Reference",
    dark_mode: bool = True,
    include_in_schema: bool = False,
) -> str:
    """Mount the Scalar API reference UI on a Rivex app.

    Args:
        app: Rivex application instance.
        path: URL path for the Scalar UI (default ``"/scalar"``).
        spec_url: URL of the OpenAPI spec. If ``None``, uses
            ``app.openapi_url`` (default ``"/openapi.json"``).
        title: Page title.
        dark_mode: Use dark theme.
        include_in_schema: Whether to list this route in the OpenAPI spec.

    Returns:
        The path where Scalar is mounted.
    """
    if spec_url is None:
        spec_url = getattr(app, "openapi_url", "/openapi.json") or "/openapi.json"

    html = render_scalar_html(spec_url=spec_url, title=title, dark_mode=dark_mode)

    @app.get(path, include_in_schema=include_in_schema)
    def _scalar_page() -> dict:
        """Render the Scalar API reference page for the mounted path.

        Captures the pre-rendered Scalar HTML from the enclosing
        ``mount_scalar`` call and returns it wrapped in an
        :class:`HTMLResponse` so the framework serves it with the
        correct ``Content-Type`` header.

        Returns:
            An ``HTMLResponse`` carrying the Scalar HTML payload.
        """
        from rivex.http.responses import HTMLResponse

        return HTMLResponse(html)

    return path
