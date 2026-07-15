"""AsyncAPI specification generator for WebSocket routes.

Usage::

    from rivex.openapi.asyncapi import build_asyncapi_html, generate_asyncapi
"""

from __future__ import annotations

from typing import Any


def generate_asyncapi(
    *,
    title: str = "Rivex WebSocket API",
    version: str = "1.0.0",
    description: str = "",
    ws_routes: list[tuple[str, Any]],
    servers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate an AsyncAPI 2.6.0 spec from registered WebSocket routes.

    Args:
        title: API title.
        version: API version string.
        description: API description.
        ws_routes: List of ``(path, handler)`` tuples from the app.
        servers: Optional list of server dicts with ``url``, ``protocol``.

    Returns:
        AsyncAPI spec as a JSON-serialisable dict.
    """
    spec: dict[str, Any] = {
        "asyncapi": "2.6.0",
        "info": {
            "title": title,
            "version": version,
        },
        "channels": {},
    }

    if description:
        spec["info"]["description"] = description

    if servers:
        spec["servers"] = {}
        for i, srv in enumerate(servers):
            spec["servers"][f"server_{i}"] = srv

    for ws_path, ws_handler in ws_routes:
        channel_name = ws_path.lstrip("/").replace("/", ".")
        summary = ""
        description = ""
        if hasattr(ws_handler, "__doc__") and ws_handler.__doc__:
            text = ws_handler.__doc__.strip()
            if "\n" in text:
                summary = text.split("\n")[0]
                description = text
            else:
                summary = text

        channel: dict[str, Any] = {}
        if summary:
            channel["description"] = description or summary

        channel["subscribe"] = {
            "message": {
                "contentType": "application/json",
                "payload": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text message frame"},
                        "data": {"type": "string", "description": "Binary message frame"},
                    },
                },
            }
        }

        channel["publish"] = {
            "message": {
                "contentType": "application/json",
                "payload": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text message frame"},
                        "data": {"type": "string", "description": "Binary message frame"},
                    },
                },
            }
        }

        spec["channels"][channel_name] = channel

    return spec


def build_asyncapi_html(asyncapi_url: str, title: str = "AsyncAPI") -> str:
    """Generate an HTML page that renders the AsyncAPI spec via the
    AsyncAPI Studio web component."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ margin: 0; padding: 0; }}
        asyncapi-component {{ display: block; height: 100vh; }}
    </style>
</head>
<body>
    <asyncapi-component
        schemaUrl="{asyncapi_url}"
        cssImport="https://unpkg.com/@asyncapi/react-component@latest/styles/default.css"
    ></asyncapi-component>
    <script src="https://unpkg.com/@asyncapi/web-component@latest/lib/asyncapi-web-component.js"></script>
</body>
</html>"""
