"""``rivex.utilities.response.header`` — header manipulation on the response dict.

Headers are stored as ``list[tuple[str, str]]`` to preserve ordering
and allow duplicates (``Set-Cookie`` typically appears multiple
times). Lookup is case-insensitive to match the request side.
"""

from __future__ import annotations

from typing import Any


class ResponseHeaderUtility:
    """Static helpers for reading and mutating ``response["headers"]``."""

    @staticmethod
    def get_response_header(response: dict[str, Any], name: str, default: str | None = None) -> str | None:
        """Return the first header value matching ``name`` (case-insensitive)."""
        headers = response.get("headers") or []
        lowered = name.lower()
        for key, value in headers:
            if isinstance(key, str) and key.lower() == lowered:
                return value
        return default

    @staticmethod
    def get_all_response_headers(response: dict[str, Any], name: str) -> list[str]:
        """Return every value for ``name`` (case-insensitive), in order."""
        headers = response.get("headers") or []
        lowered = name.lower()
        return [value for key, value in headers if isinstance(key, str) and key.lower() == lowered]

    @staticmethod
    def set_response_header(response: dict[str, Any], name: str, value: str) -> None:
        """Set ``name`` to ``value``, replacing any previous entries for the same name."""
        headers = list(response.get("headers") or [])
        lowered = name.lower()
        headers = [(key, val) for key, val in headers if not (isinstance(key, str) and key.lower() == lowered)]
        headers.append((name, value))
        response["headers"] = headers

    @staticmethod
    def add_response_header(response: dict[str, Any], name: str, value: str) -> None:
        """Append ``(name, value)`` without disturbing existing entries (allows duplicates)."""
        headers = list(response.get("headers") or [])
        headers.append((name, value))
        response["headers"] = headers

    @staticmethod
    def remove_response_header(response: dict[str, Any], name: str) -> bool:
        """Strip every header whose name matches ``name`` (case-insensitive). Returns ``True`` if any were removed."""
        headers = response.get("headers") or []
        lowered = name.lower()
        kept = [(k, v) for k, v in headers if not (isinstance(k, str) and k.lower() == lowered)]
        removed = len(kept) != len(headers)
        response["headers"] = kept
        return removed

    @staticmethod
    def has_response_header(response: dict[str, Any], name: str) -> bool:
        """Return ``True`` when ``name`` is present (case-insensitive)."""
        headers = response.get("headers") or []
        lowered = name.lower()
        return any(isinstance(k, str) and k.lower() == lowered for k, _ in headers)

    @staticmethod
    def get_response_status(response: dict[str, Any], default: int = 200) -> int:
        """Return ``response["status"]`` (defaulting to ``200`` for stream-style responses)."""
        return int(response.get("status", default))

    @staticmethod
    def set_response_status(response: dict[str, Any], status: int) -> None:
        """Replace ``response["status"]`` with ``status``."""
        response["status"] = int(status)


__all__ = ["ResponseHeaderUtility"]
