"""``rivex.utilities.request.param`` — path / query / cookie accessors.

Three bags are exposed on ``request_data``:

* ``path_params``  — extracted from the matched route (e.g. ``/users/{id}``)
* ``query_string`` — raw query string (``"a=1&b=2"``) plus an optional
  ``query`` dict parsed by the framework
* ``cookies``      — parsed cookie header as ``dict[str, str]``
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs


class RequestParamUtility:
    """Static helpers for reading and writing request parameters."""

    @staticmethod
    def get_path_param(request_data: dict[str, Any], name: str, default: Any = None) -> Any:
        """Return ``request_data["path_params"][name]`` (or ``default``)."""
        path_params = request_data.get("path_params") or {}
        return path_params.get(name, default)

    @staticmethod
    def set_path_param(request_data: dict[str, Any], name: str, value: Any) -> None:
        """Add or overwrite a single path parameter."""
        path_params = dict(request_data.get("path_params") or {})
        path_params[name] = value
        request_data["path_params"] = path_params

    @staticmethod
    def get_path_params(request_data: dict[str, Any]) -> dict[str, Any]:
        """Return a shallow copy of every path parameter."""
        return dict(request_data.get("path_params") or {})

    @staticmethod
    def get_query_string(request_data: dict[str, Any]) -> str:
        """Return the raw query string (``""`` when absent)."""
        return request_data.get("query_string") or ""

    @staticmethod
    def set_query_string(request_data: dict[str, Any], query_string: str) -> None:
        """Replace the raw query string. The cached ``query`` dict (if any) is invalidated."""
        request_data["query_string"] = query_string
        request_data.pop("query", None)

    @staticmethod
    def get_query_params(request_data: dict[str, Any]) -> dict[str, list[str]]:
        """Parse the raw query string into a ``{name: [values]}`` mapping.

        Repeated query keys yield a list with one entry per occurrence.
        """
        cached = request_data.get("query")
        if isinstance(cached, dict):
            return cached
        parsed = parse_qs(RequestParamUtility.get_query_string(request_data), keep_blank_values=True)
        request_data["query"] = parsed
        return parsed

    @staticmethod
    def get_query_value(request_data: dict[str, Any], name: str, default: str | None = None) -> str | None:
        """Return the first value associated with ``name`` in the query string."""
        params = RequestParamUtility.get_query_params(request_data)
        values = params.get(name)
        return values[0] if values else default

    @staticmethod
    def get_cookies(request_data: dict[str, Any]) -> dict[str, str]:
        """Parse the ``Cookie`` header into a flat ``dict`` (last-write-wins on duplicate keys)."""
        cookies = request_data.get("cookies")
        if isinstance(cookies, dict):
            return cookies
        header = None
        for key, value in request_data.get("headers") or []:
            if isinstance(key, str) and key.lower() == "cookie":
                header = value
                break
        parsed: dict[str, str] = {}
        if header:
            for chunk in header.split(";"):
                chunk = chunk.strip()
                if not chunk or "=" not in chunk:
                    continue
                k, v = chunk.split("=", 1)
                parsed[k.strip()] = v.strip()
        request_data["cookies"] = parsed
        return parsed

    @staticmethod
    def get_cookie(request_data: dict[str, Any], name: str, default: str | None = None) -> str | None:
        """Return the value of cookie ``name`` (``default`` when absent)."""
        return RequestParamUtility.get_cookies(request_data).get(name, default)

    @staticmethod
    def dump_query_params_as_json(request_data: dict[str, Any]) -> str:
        """Render the parsed query params as a compact JSON string. Useful for logging."""
        return json.dumps(RequestParamUtility.get_query_params(request_data), default=str)


__all__ = ["RequestParamUtility"]
