"""``rivex.utilities.request.header`` — header manipulation on the raw request dict.

Headers are stored as ``list[tuple[str, str]]`` to preserve ordering
and allow duplicate header names. Lookup is case-insensitive to
match the rest of the framework.
"""

from __future__ import annotations

from typing import Any


class RequestHeaderUtility:
    """Static helpers for reading and mutating ``request_data["headers"]``."""

    @staticmethod
    def get_request_header(request_data: dict[str, Any], name: str, default: str | None = None) -> str | None:
        """Return the value of the first header whose name matches ``name`` (case-insensitive)."""
        headers = request_data.get("headers") or []
        lowered = name.lower()
        for key, value in headers:
            if isinstance(key, str) and key.lower() == lowered:
                return value
        return default

    @staticmethod
    def get_all_request_headers(request_data: dict[str, Any], name: str) -> list[str]:
        """Return every value associated with ``name`` (case-insensitive), in order."""
        headers = request_data.get("headers") or []
        lowered = name.lower()
        return [value for key, value in headers if isinstance(key, str) and key.lower() == lowered]

    @staticmethod
    def set_request_header(request_data: dict[str, Any], name: str, value: str) -> None:
        """Set ``name`` to ``value``, removing any previous entries for the same name."""
        headers = list(request_data.get("headers") or [])
        lowered = name.lower()
        headers = [(key, val) for key, val in headers if not (isinstance(key, str) and key.lower() == lowered)]
        headers.append((name, value))
        request_data["headers"] = headers

    @staticmethod
    def add_request_header(request_data: dict[str, Any], name: str, value: str) -> None:
        """Append ``(name, value)`` without disturbing existing entries (allows duplicates)."""
        headers = list(request_data.get("headers") or [])
        headers.append((name, value))
        request_data["headers"] = headers

    @staticmethod
    def remove_request_header(request_data: dict[str, Any], name: str) -> bool:
        """Strip every header whose name matches ``name`` (case-insensitive). Returns ``True`` if any were removed."""
        headers = request_data.get("headers") or []
        lowered = name.lower()
        kept = [(k, v) for k, v in headers if not (isinstance(k, str) and k.lower() == lowered)]
        removed = len(kept) != len(headers)
        request_data["headers"] = kept
        return removed

    @staticmethod
    def has_request_header(request_data: dict[str, Any], name: str) -> bool:
        """Return ``True`` when ``name`` is present (case-insensitive)."""
        headers = request_data.get("headers") or []
        lowered = name.lower()
        return any(isinstance(k, str) and k.lower() == lowered for k, _ in headers)


__all__ = ["RequestHeaderUtility"]
