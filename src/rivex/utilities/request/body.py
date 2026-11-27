"""``rivex.utilities.request.body`` — request body accessors.

The raw body is stored on ``request_data["body"]`` as ``bytes`` (or
``b""`` when absent). Most handlers don't read bytes directly —
they go through Pydantic / msgspec / JSON parsing helpers — but
a small set of static helpers still need direct access (file
uploads, streaming, raw form parsing).
"""

from __future__ import annotations

import json
from typing import Any


class RequestBodyUtility:
    """Static helpers for reading and replacing ``request_data["body"]``."""

    @staticmethod
    def get_request_body(request_data: dict[str, Any]) -> bytes:
        """Return the raw body bytes (``b""`` when absent)."""
        body = request_data.get("body", b"")
        return body if isinstance(body, (bytes, bytearray)) else bytes(body)

    @staticmethod
    def set_request_body(request_data: dict[str, Any], body: bytes) -> None:
        """Replace the body with ``body``."""
        request_data["body"] = body

    @staticmethod
    def get_request_body_size(request_data: dict[str, Any]) -> int:
        """Return the body length in bytes (0 when absent)."""
        return len(RequestBodyUtility.get_request_body(request_data))

    @staticmethod
    def get_request_body_text(request_data: dict[str, Any], encoding: str = "utf-8") -> str:
        """Decode the body to text using ``encoding`` (default UTF-8)."""
        return RequestBodyUtility.get_request_body(request_data).decode(encoding, errors="replace")

    @staticmethod
    def get_request_body_json(request_data: dict[str, Any]) -> Any:
        """Parse the body as JSON and return the decoded value (``None`` when empty)."""
        body = RequestBodyUtility.get_request_body(request_data)
        if not body:
            return None
        return json.loads(body)


__all__ = ["RequestBodyUtility"]
