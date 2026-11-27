"""``rivex.middleware.api_key_leak`` — auto-strip accidentally exposed API keys / secrets from response bodies.

Walks every JSON response and redacts string values that match any of
the framework's known secret formats (``sk_live_*``, ``ghp_*``, JWT
tokens, generic ``key=value`` patterns). Also flags fields whose
**name** looks like a secret slot (``api_key``, ``password``, …).

The middleware never throws — it logs and silently rewrites the body.
Routes that legitimately return secrets (e.g. key-creation
endpoints) can be added to ``allowed_paths`` so the middleware
skips them.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Sequence
from typing import Any, Optional

from rivex.constants.regex import Regex
from rivex.middleware.abstraction import IMiddleware


def _json_body(body: Any) -> Optional[Any]:
    """Decode a JSON body into a Python value, tolerating common encodings.

    Accepts bytes/bytearray (decoded as UTF-8 first), ``str`` (parsed
    directly), and any pre-decoded Python value which is returned
    untouched. Decoding failures — invalid UTF-8 or invalid JSON — return
    ``None`` so callers can detect them without exception handling.

    Args:
        body: The raw body value. May be bytes, a string, or a
            pre-decoded JSON value.

    Returns:
        The decoded JSON value, the original value if it was neither
        bytes nor string, or ``None`` if decoding failed.
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


def _normalize_allowed(allowed: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split allowed entries into ``(paths, names)``.

    Entries starting with ``"/"`` (or containing a path separator) are
    treated as path globs; everything else is treated as a route name
    (``RouteRecord.name``).
    """
    paths: list[str] = []
    names: list[str] = []
    for entry in allowed:
        if not entry:
            continue
        if entry.startswith("/") or "/" in entry:
            paths.append(entry)
        else:
            names.append(entry)
    return paths, names


def _path_matches(path: str, patterns: Sequence[str]) -> bool:
    """Return ``True`` when ``path`` matches any glob in ``patterns``.

    Each pattern is tested as either an exact match or as a prefix
    glob (entries ending in ``"*"`` match every ``path`` that starts
    with the preceding characters).

    Args:
        path: The request path to test.
        patterns: Sequence of glob patterns to test against.

    Returns:
        ``True`` when ``path`` matches any pattern, ``False`` otherwise.
    """
    for pattern in patterns:
        if pattern.endswith("*") and path.startswith(pattern[:-1]):
            return True
        if path == pattern:
            return True
    return False


class APIKeyLeakMiddleware(IMiddleware):
    """Strip accidentally exposed API keys / secrets from response JSON.

    Parameters:
        custom_key_patterns: Regexes that match suspicious field names
            (merged with :data:`Regex.DEFAULT_KEY_NAMES`).
        custom_value_patterns: Regexes that match suspicious string
            values (merged with :data:`Regex.DEFAULT_VALUES`).
        replacement: Replacement string for redacted values. Default
            ``"[REDACTED]"``.
        path_predicate: ``Callable[[str], bool]`` — only inspect these
            paths (``None`` means every path).
        excluded_paths: Paths to skip entirely (exact match plus ``"*"``
            suffix glob). Routes that legitimately return secrets should
            be listed here. Kept for back-compat — prefer ``allowed_paths``.
        allowed_paths: Allow-list of paths / route names that are
            **expected** to return secrets (key-creation endpoints,
            Stripe / Razorpay webhook receivers, etc.). The middleware
            skips these routes. Entries are interpreted as:

            * Path globs (entries starting with ``"/"`` or containing
              ``"/"``): exact match plus ``"*"`` suffix glob
              (``"/admin/api-keys*"`` matches ``/admin/api-keys/create``).
            * Route names (entries without ``"/"``): matched against
              ``RouteRecord.name`` resolved from
              ``request_data["route_name"]`` (the ASGI adapter stamps
              this on every request after route lookup).

            Equivalent to ``excluded_paths`` for path entries; route-name
            entries are the new piece. Pass one or the other (or both).
        routes: Optional sequence of route records (with ``.name`` and
            ``.path``). Required for route-name allow-list entries to
            resolve. Pass ``app._routes`` once at startup.
        logger_name: Name of the stdlib logger to emit warnings on.
    """

    def __init__(
        self,
        *,
        custom_key_patterns: Sequence[str | re.Pattern[str]] = (),
        custom_value_patterns: Sequence[str | re.Pattern[str]] = (),
        replacement: str = "[REDACTED]",
        path_predicate: Optional[Callable[[str], bool]] = None,
        excluded_paths: Sequence[str] = (),
        allowed_paths: Sequence[str] = (),
        routes: Optional[Sequence[Any]] = None,
        logger_name: str = "rivex.api_key_leak",
    ) -> None:
        key_patterns: list[str | re.Pattern[str]] = list(Regex.DEFAULT_KEY_NAMES) + list(custom_key_patterns)
        value_patterns: list[str | re.Pattern[str]] = list(Regex.DEFAULT_VALUES) + list(custom_value_patterns)
        self._key_regexes: list[re.Pattern[str]] = Regex.compile_patterns(key_patterns)
        self._value_regexes: list[re.Pattern[str]] = Regex.compile_patterns(value_patterns)
        self.replacement = replacement

        # Build the allow-list lookup table once at construction time.
        allowed_path_globs, allowed_route_names = _normalize_allowed(allowed_paths)
        excluded_path_globs, _ = _normalize_allowed(excluded_paths)
        self._allowed_paths: tuple[str, ...] = tuple(allowed_path_globs + excluded_path_globs)
        self._allowed_names: frozenset[str] = frozenset(allowed_route_names)
        self._name_for_path: dict[str, str] = {}
        if routes is not None:
            for r in routes:
                name = getattr(r, "name", None)
                path = getattr(r, "path", None)
                if name and path:
                    self._name_for_path[str(path)] = str(name)

        self._path_predicate = path_predicate
        self._logger = logging.getLogger(logger_name)

    def _is_allowed(self, request_data: dict, path: str) -> bool:
        """Return ``True`` when this request sits on a path / route the user opted out of."""
        if self._path_predicate is not None and not self._path_predicate(path):
            return True
        if self._allowed_paths and _path_matches(path, self._allowed_paths):
            return True
        route_name = request_data.get("route_name")
        if route_name and route_name in self._allowed_names:
            return True
        # Also support ``request_data["matched_route_name"]`` (alternate stamp)
        route_name = request_data.get("matched_route_name")
        if route_name and route_name in self._allowed_names:
            return True
        return False

    def _value_is_secret(self, value: str) -> bool:
        """Return ``True`` when ``value`` looks like an exposed secret.

    Tests every configured value-shape regex against ``value`` and two
    normalized variants — a stripped version (whitespace removed) and
    one with surrounding ``"``/``'`` characters stripped as well — so
    that JSON-encoded values such as ``"sk_live_…"`` still match the
    patterns in :data:`Regex.DEFAULT_VALUES`.

    Args:
        value: The candidate string to test.

    Returns:
        ``True`` when any configured regex matches the raw or
        normalized forms of ``value``.
    """
        # Strip surrounding quotes / whitespace so JSON-encoded values
        # (``"sk_live_…"``) match the patterns stored in ``Regex.DEFAULT_VALUES``.
        candidates = (value, value.strip().strip('"').strip("'"))
        for regex in self._value_regexes:
            for candidate in candidates:
                if regex.search(candidate):
                    return True
        return False

    def _key_is_secret(self, key: str) -> bool:
        """Return ``True`` when the dict key name suggests a secret field.

    Args:
        key: The dict key to test.

    Returns:
        ``True`` when at least one configured key-name regex matches
        ``key`` (e.g. ``"api_key"``, ``"password"``).
    """
        for regex in self._key_regexes:
            if regex.search(key):
                return True
        return False

    def _redact(self, data: Any, hits: list[str], path: str = "") -> Any:
        """Recursively walk ``data`` and replace any secret field.

    Dicts are traversed key-by-key. A key wins replacement when its
    name matches :meth:`_key_is_secret`; otherwise a string value wins
    when it matches :meth:`_value_is_secret`. Lists are traversed
    index-by-index. Each replacement appends a tagged entry to
    ``hits`` so callers can audit which keys vs. values fired.

    Args:
        data: A JSON-compatible Python value to walk.
        hits: Mutable accumulator; matching JSON-pointer-like paths
            (tagged with the match reason) are appended here.
        path: Internal recursion cursor. Pass ``""`` at the top level.

    Returns:
        A new structure of the same shape as ``data`` with secret
        fields replaced. Scalars are returned unchanged.
    """
        if isinstance(data, dict):
            cleaned: dict = {}
            for key, value in data.items():
                field_path = f"{path}.{key}" if path else str(key)
                if isinstance(key, str) and self._key_is_secret(key):
                    hits.append(f"{field_path} (key-name match)")
                    cleaned[key] = self.replacement
                elif isinstance(value, str) and self._value_is_secret(value):
                    hits.append(f"{field_path} (value-shape match)")
                    cleaned[key] = self.replacement
                else:
                    cleaned[key] = self._redact(value, hits, field_path)
            return cleaned
        if isinstance(data, list):
            return [self._redact(item, hits, f"{path}[{idx}]" if path else f"[{idx}]")
                    for idx, item in enumerate(data)]
        return data

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and strip leaked secrets from the response.

    Invokes ``call_next`` to obtain the downstream response. Skips the
    request entirely when :meth:`_is_allowed` reports the path or route
    is on the opt-out list. Otherwise decodes the response body, walks
    it via :meth:`_redact`, and — only when at least one field was
    actually stripped — re-serializes the rewritten body as compact
    UTF-8 JSON and replaces ``response["body"]``. A warning is emitted
    on the configured logger listing the stripped field paths so
    operators can audit where the auto-redaction is firing.

    Args:
        request_data: The in-flight request envelope. The ``path`` and
            route-name keys are used by the allow-list check.
        call_next: Awaitable that invokes the next middleware/handler
            and returns the downstream response dict.

    Returns:
        The downstream response dict, with ``body`` replaced by the
        re-serialized redacted body when at least one field was
        stripped. Unchanged otherwise.
    """
        response = await call_next(request_data)
        path = request_data.get("path") or ""
        if self._is_allowed(request_data, path):
            return response

        parsed = _json_body(response.get("body"))
        if not isinstance(parsed, (dict, list)):
            return response

        hits: list[str] = []
        redacted = self._redact(parsed, hits)
        if not hits:
            return response

        self._logger.warning(
            "Auto-stripped exposed API keys / secrets from response",
            extra={"path": path, "stripped_fields": sorted(set(hits))},
        )
        response["body"] = json.dumps(redacted, separators=(",", ":")).encode("utf-8")
        return response


__all__ = ["APIKeyLeakMiddleware"]
