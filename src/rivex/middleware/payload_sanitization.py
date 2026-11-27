"""``rivex.middleware.payload_sanitization`` — HTML-escape string fields in JSON payloads.

Walks every JSON body in flight (request and response) and HTML-escapes
strings that look like they're meant to be displayed verbatim. Useful
for sanitizing markdown / rich-text fields that callers might submit
with raw HTML — the middleware can either escape or strip depending on
:attr:`Mode`.

By default the middleware **escapes** (HTML entity-encodes) rather than
strips, so legitimate content like ``<3`` survives as ``&lt;3``.
"""

from __future__ import annotations

import html
import json
from collections.abc import Callable
from enum import Enum
from typing import Any, Iterable, Optional

from rivex.middleware.abstraction import IMiddleware


class SanitizeMode(str, Enum):
    """How to handle detected HTML in string fields."""

    ESCAPE = "escape"
    STRIP = "strip"
    NONE = "none"


class PayloadSanitizationMiddleware(IMiddleware):
    """HTML-escape or strip-detected-tags across every JSON body in flight.

    Parameters:
        mode: :attr:`SanitizeMode.ESCAPE` (default), ``STRIP`` to remove
            tags entirely, or ``NONE`` to disable.
        path_predicate: ``Callable[[str], bool]`` — only sanitise paths
            that match. ``None`` means every path.
        sanitiser: Override the HTML handler. ``None`` uses stdlib
            :func:`html.escape` (escape) or :func:`re.sub` (strip).
        max_depth: Bail out of recursive walking after this many nesting
            levels (defends against pathological payloads).
        exclude_field_names: Skip these field names (case-sensitive).
            Useful for fields like ``"raw_html"`` where the caller
            really does want raw HTML.
    """

    def __init__(
        self,
        mode: SanitizeMode = SanitizeMode.ESCAPE,
        *,
        path_predicate: Optional[Callable[[str], bool]] = None,
        sanitiser: Optional[Callable[[str], str]] = None,
        max_depth: int = 32,
        exclude_field_names: Iterable[str] = (),
    ) -> None:
        self.mode = SanitizeMode(mode)
        self._path_predicate = path_predicate
        self._sanitiser = sanitiser
        self.max_depth = max_depth
        self._exclude = set(exclude_field_names)

    def _should_run(self, path: str) -> bool:
        """Return ``True`` when sanitisation should run for ``path``.

        Always ``True`` when no path predicate is configured; otherwise
        the predicate is consulted.

        Args:
            path: The request path string.

        Returns:
            ``True`` when the request / response body should be walked
            and sanitised, ``False`` to leave it untouched.
        """
        return self._path_predicate is None or self._path_predicate(path)

    def _handle_string(self, value: str) -> str:
        """Apply the configured sanitisation mode to a single string leaf.

        In :attr:`SanitizeMode.NONE` mode the value is returned
        unchanged. With a caller-supplied ``sanitiser`` callable, that
        callable is used directly. Otherwise :attr:`SanitizeMode.ESCAPE`
        delegates to :func:`html.escape` and :attr:`SanitizeMode.STRIP`
        removes ``<...>`` substrings via :func:`re.sub`.

        Args:
            value: The raw string to sanitise.

        Returns:
            The sanitised string. May be the original value when the
            mode is ``NONE`` or no transformation was needed.
        """
        if self.mode is SanitizeMode.NONE:
            return value
        if self._sanitiser is not None:
            return self._sanitiser(value)
        if self.mode is SanitizeMode.ESCAPE:
            return html.escape(value)
        # STRIP
        import re as _re

        return _re.sub(r"<[^>]*>", "", value)

    def _walk(self, obj: Any, depth: int = 0) -> tuple[Any, bool]:
        """Return ``(new_obj, was_changed)`` after sanitising any string leaves."""
        if depth > self.max_depth:
            return obj, False
        if isinstance(obj, str):
            new = self._handle_string(obj)
            return new, new != obj
        if isinstance(obj, list):
            changed = False
            out: list = []
            for item in obj:
                new_item, item_changed = self._walk(item, depth + 1)
                out.append(new_item)
                changed = changed or item_changed
            return out, changed
        if isinstance(obj, dict):
            changed = False
            out_dict: dict = {}
            for key, value in obj.items():
                if isinstance(key, str) and key in self._exclude:
                    out_dict[key] = value
                    continue
                new_value, value_changed = self._walk(value, depth + 1)
                out_dict[key] = new_value
                changed = changed or value_changed
            return out_dict, changed
        return obj, False

    def _process_json_body(self, body: Any) -> tuple[Any, bool]:
        """Thin wrapper around :meth:`_walk` for response-body processing.

        Args:
            body: A JSON-compatible Python value (or a pre-decoded
                payload already in the right shape).

        Returns:
            A 2-tuple of ``(new_body, was_changed)`` — see
            :meth:`_walk` for the exact semantics.
        """
        return self._walk(body)

    @staticmethod
    def _coerce_body(body: Any) -> Any:
        """Decode ``body`` into a JSON value when it is bytes or ``str``.

        Bytes and bytearray inputs are decoded as UTF-8 then parsed;
        strings are parsed directly. Decoding errors (invalid UTF-8 or
        invalid JSON) return ``None`` so callers can detect them
        without exception handling. Any other type is returned as-is.

        Args:
            body: The raw body value (bytes, ``str``, or a pre-decoded
                value).

        Returns:
            The decoded JSON value, the original value if it was neither
            bytes nor string, or ``None`` on decode failure.
        """
        if isinstance(body, (bytes, bytearray)):
            try:
                return json.loads(bytes(body).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return None
        return body

    @staticmethod
    def _dump(value: Any) -> bytes:
        """Serialise ``value`` as compact UTF-8 JSON bytes.

        Args:
            value: Any JSON-serialisable Python value.

        Returns:
            ``value`` rendered with the standard library ``json`` module
            using the ``(",", ":")`` separator pair (no whitespace),
            encoded as UTF-8.
        """
        return json.dumps(value, separators=(",", ":")).encode("utf-8")

    async def process(self, request_data: dict, call_next) -> dict:
        """Sanitise JSON strings on both the request and response bodies.

        On ``POST`` / ``PUT`` / ``PATCH`` requests whose path passes
        :meth:`_should_run`, the request body is decoded via
        :meth:`_coerce_body` and walked via :meth:`_process_json_body` —
        any sanitised fields are re-serialised with :meth:`_dump` and
        the result replaces ``request_data["body"]``. On the way back
        the same walk is applied to the downstream response body
        (provided :meth:`_should_run` is still true), so handlers that
        echo request data also see sanitised output.

        Args:
            request_data: The in-flight request envelope. ``method``,
                ``path``, and ``body`` are read; ``body`` may be
                replaced.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            The downstream response dict, with ``body`` re-serialised
            when sanitisation actually changed a string field. Unchanged
            otherwise.
        """
        method = (request_data.get("method") or "").upper()
        path = request_data.get("path") or ""

        if self._should_run(path) and method in {"POST", "PUT", "PATCH"}:
            parsed = self._coerce_body(request_data.get("body"))
            if isinstance(parsed, (dict, list)):
                new_obj, changed = self._process_json_body(parsed)
                if changed:
                    request_data["body"] = self._dump(new_obj)

        response = await call_next(request_data)

        if self._should_run(path):
            parsed = self._coerce_body(response.get("body"))
            if isinstance(parsed, (dict, list)):
                new_obj, changed = self._process_json_body(parsed)
                if changed:
                    response["body"] = self._dump(new_obj)

        return response


__all__ = ["SanitizeMode", "PayloadSanitizationMiddleware"]
