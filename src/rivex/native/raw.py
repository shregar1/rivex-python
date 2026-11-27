"""Fast response helpers for zero-overhead response building.

Provides :func:`raw_response` — a helper that lets handlers skip the
framework's response normalization layer entirely. The handler
serialises its own body (typically via ``rivex_core.json_serialize``)
and returns a pre-built response dict marked with ``_rivex_raw``.

The ``direct_wrapper`` in ``_injection.py`` detects this marker and
passes the dict straight through to the Rust core, skipping
``_normalize_response_fast`` (~2-5 µs saved per request).

Example::

    from rivex_core import json_serialize
    from rivex.native.raw import raw_response

    @app.get("/users/{id}")
    def get_user(id: int):
        user = db.fetch_one(id)
        return raw_response(
            body=json_serialize(user),
            content_type="application/json",
        )

This is purely a response-pipeline optimisation — it works with any
data source (database, cache, file, computation). The handler decides
how to build the body bytes; the framework skips normalisation.
"""

from __future__ import annotations

_JSON_HEADERS = [("content-type", "application/json")]
_TEXT_HEADERS = [("content-type", "text/plain; charset=utf-8")]
_HTML_HEADERS = [("content-type", "text/html; charset=utf-8")]


def raw_response(
    body: bytes,
    *,
    status: int = 200,
    headers: list[tuple[str, str]] | None = None,
    content_type: str | None = None,
) -> dict:
    """Build a pre-normalised response dict that skips the framework pipeline.

    Args:
        body: Pre-serialised response body as bytes.
        status: HTTP status code.
        headers: Full header list. If provided, ``content_type`` is ignored.
        content_type: If ``headers`` is None, builds a single
            ``Content-Type`` header from this value.
            Defaults to ``"application/json"``.

    Returns:
        A dict with ``_rivex_raw=True``, ``status``, ``headers``, and
        ``body`` keys. The ``direct_wrapper`` detects ``_rivex_raw``
        and passes this dict straight to Rust without calling
        ``_normalize_response_fast``.
    """
    if headers is None:
        ct = content_type or "application/json"
        headers = [("content-type", ct)]
    return {
        "_rivex_raw": True,
        "status": status,
        "headers": headers,
        "body": body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8"),
    }


def raw_json(body: bytes, status: int = 200) -> dict:
    """Shortcut for ``raw_response(body, content_type="application/json")``."""
    return {
        "_rivex_raw": True,
        "status": status,
        "headers": _JSON_HEADERS,
        "body": body if isinstance(body, (bytes, bytearray)) else bytes(body),
    }


def raw_text(body: bytes | str, status: int = 200) -> dict:
    """Shortcut for ``raw_response(body, content_type="text/plain")``."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    return {
        "_rivex_raw": True,
        "status": status,
        "headers": _TEXT_HEADERS,
        "body": body,
    }


def raw_html(body: bytes | str, status: int = 200) -> dict:
    """Shortcut for ``raw_response(body, content_type="text/html")``."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    return {
        "_rivex_raw": True,
        "status": status,
        "headers": _HTML_HEADERS,
        "body": body,
    }
