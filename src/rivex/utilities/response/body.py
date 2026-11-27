"""``rivex.utilities.response.body`` — body read / write helpers.

Rivex accepts three interchangeable body shapes on the response
dict — the framework serialises whichever one is present:

* ``body``      — raw ``bytes`` (or ``str`` for text responses)
* ``body_json`` — any JSON-serialisable value; encoded by the framework
* ``body_file`` — a path string or file-like object streamed to the client

The helpers below normalise reads to ``bytes`` and centralise the
shortcuts (``set_json``, ``set_text``, ``set_empty``).
"""

from __future__ import annotations

import json
from typing import Any


class ResponseBodyUtility:
    """Static helpers for reading and replacing ``response`` body fields."""

    @staticmethod
    def get_response_body(response: dict[str, Any]) -> bytes:
        """Return ``response["body"]`` as ``bytes`` (empty ``b""`` when absent)."""
        body = response.get("body", b"")
        if isinstance(body, (bytes, bytearray)):
            return bytes(body)
        if isinstance(body, str):
            return body.encode("utf-8")
        return b""

    @staticmethod
    def set_response_body(response: dict[str, Any], body: bytes | str) -> None:
        """Replace ``response["body"]`` and clear ``body_json`` / ``body_file`` so only one shape wins."""
        if isinstance(body, str):
            body = body.encode("utf-8")
        response["body"] = bytes(body)
        response.pop("body_json", None)
        response.pop("body_file", None)

    @staticmethod
    def set_response_body_json(response: dict[str, Any], value: Any) -> None:
        """Stage ``value`` for JSON encoding by setting ``response["body_json"]``."""
        response["body_json"] = value
        response.pop("body", None)
        response.pop("body_file", None)

    @staticmethod
    def set_response_body_text(response: dict[str, Any], text: str, *, encoding: str = "utf-8") -> None:
        """Shortcut for ``set_response_body(text.encode(encoding))``."""
        ResponseBodyUtility.set_response_body(response, text.encode(encoding))

    @staticmethod
    def set_empty_response(response: dict[str, Any], *, status: int = 204) -> None:
        """Reset the response to a ``status``-only envelope with no body — typical for ``204 No Content``."""
        response["status"] = int(status)
        response.pop("body", None)
        response.pop("body_json", None)
        response.pop("body_file", None)

    @staticmethod
    def get_response_body_size(response: dict[str, Any]) -> int:
        """Return the byte length of the body (0 when absent / JSON-encoded)."""
        if "body" in response:
            return len(ResponseBodyUtility.get_response_body(response))
        if "body_json" in response:
            try:
                return len(json.dumps(response["body_json"], default=str).encode("utf-8"))
            except (TypeError, ValueError):
                return 0
        return 0


__all__ = ["ResponseBodyUtility"]
