"""``rivex.middleware.pii_redaction`` — auto-redact PII fields in response bodies.

Walks every JSON response and replaces any string value that matches
a PII regex (SSN, credit-card, etc.) with ``[REDACTED]``. Logs which
paths were redacted so dev tooling can find missing masks. Excludes
configured paths (e.g. ``/admin/users`` where masked PII is expected).
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
    ``None`` so they can be detected and skipped by callers without
    exception handling.

    Args:
        body: The raw body value pulled off a response. May be bytes,
            a string, or a pre-decoded JSON value.

    Returns:
        The decoded JSON value, the original value if it was not bytes
        or string, or ``None`` if decoding failed.
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


def _path_matches(path: str, patterns: Sequence[str]) -> bool:
    """Return ``True`` when *path* matches any glob in *patterns* (exact or ``"*"`` suffix)."""
    for pattern in patterns:
        if pattern.endswith("*") and path.startswith(pattern[:-1]):
            return True
        if path == pattern:
            return True
    return False


def _strip_separators(value: str) -> str:
    """Remove ``-`` and `` `` characters from ``value``.

    Used by PII matching to normalize credit-card-like numbers before
    running the digit-only regex fallback (e.g. ``"1234-5678 9012-3456"``
    → ``"1234567890123456"``).

    Args:
        value: The string to normalize.

    Returns:
        ``value`` with all hyphens and ASCII spaces removed.
    """
    return value.replace("-", "").replace(" ", "")


class PIIRedactionMiddleware(IMiddleware):
    """Mask PII regex matches in every JSON response body.

    Parameters:
        patterns: List of regex patterns that flag PII. Defaults to
            :data:`Regex.SSN` and :data:`Regex.CARD`.
        replacement: Replacement string substituted for the PII value.
            Default ``"[REDACTED]"``.
        path_predicate: ``Callable[[str], bool]`` — only inspect these
            paths (``None`` means every path).
        excluded_paths: Paths to skip entirely (exact match plus ``"*"``
            suffix glob). Kept for back-compat — prefer ``allowed_paths``.
        allowed_paths: Allow-list of paths / route names that are
            **expected** to return PII (e.g. ``/admin/users/{id}`` where
            the operator UI shows raw SSNs). Same path / route-name
            semantics as :class:`APIKeyLeakMiddleware`.
        routes: Optional sequence of route records (with ``.name`` and
            ``.path``). Required for route-name allow-list entries to
            resolve. Pass ``app._routes`` once at startup.
        logger_name: Name of the stdlib logger to emit redacted-path
            warnings on.
    """

    def __init__(
        self,
        *,
        patterns: Sequence[str] = (Regex.SSN, Regex.CARD),
        replacement: str = "[REDACTED]",
        path_predicate: Optional[Callable[[str], bool]] = None,
        excluded_paths: Sequence[str] = (),
        allowed_paths: Sequence[str] = (),
        routes: Optional[Sequence[Any]] = None,
        logger_name: str = "rivex.pii_redaction",
    ) -> None:
        self._regexes: list[re.Pattern[str]] = [
            p if isinstance(p, re.Pattern) else re.compile(p)
            for p in patterns
        ]
        self.replacement = replacement
        self._path_predicate = path_predicate

        allowed_path_globs: list[str] = list(excluded_paths) + list(allowed_paths)
        self._allowed_paths: tuple[str, ...] = tuple(allowed_path_globs)
        allowed_route_names: list[str] = [
            e for e in allowed_paths if not (e.startswith("/") or "/" in e)
        ]
        self._allowed_names: frozenset[str] = frozenset(allowed_route_names)
        self._name_for_path: dict[str, str] = {}
        if routes is not None:
            for r in routes:
                name = getattr(r, "name", None)
                path = getattr(r, "path", None)
                if name and path:
                    self._name_for_path[str(path)] = str(name)

        self._logger = logging.getLogger(logger_name)
        self._extra_card_regex = re.compile(Regex.CARD)
        self._strip = _strip_separators

    def _is_allowed(self, request_data: dict, path: str) -> bool:
        """Decide whether this request path is exempt from PII redaction.

    Bails out (returns ``True``) when the configured path predicate
    rejects the path, when the path matches one of the allow-listed
    path globs, or when the resolved route name is in the allow list.
    Otherwise returns ``False`` to mean the response body should be
    scanned.

    Args:
        request_data: The request envelope; used only to read the
            ``route_name`` / ``matched_route_name`` fields.
        path: The request path string, used to check the predicate and
            the path-glob allow list.

    Returns:
        ``True`` when this middleware should skip redaction for the
        current request, ``False`` otherwise.
    """
        if self._path_predicate is not None and not self._path_predicate(path):
            return True
        if self._allowed_paths and _path_matches(path, self._allowed_paths):
            return True
        route_name = request_data.get("route_name") or request_data.get("matched_route_name")
        if route_name and route_name in self._allowed_names:
            return True
        return False

    def _looks_like_pii(self, value: str) -> bool:
        """Return ``True`` when ``value`` looks like PII under any configured regex.

    First runs every configured PII regex against the raw value. If
    none match, applies the loose credit-card fallback: the value is
    stripped of ``-`` and spaces, the resulting digit count must be
    between 12 and 19, and the extra-card regex must match the
    digits-only form.

    Args:
        value: The candidate string to classify.

    Returns:
        ``True`` when the value should be treated as PII and redacted.
    """
        for regex in self._regexes:
            if regex.match(value):
                return True
        # Loose credit-card match on digits-only form (e.g. "1234 5678 9012 3456")
        if 12 <= len(self._strip(value)) <= 19 and self._extra_card_regex.match(self._strip(value)):
            return True
        return False

    def _redact(self, data: Any, hits: list[str], path: str = "") -> Any:
        """Recursively walk ``data`` and replace every PII string in place.

    Dicts are traversed key-by-key, and any string value classified by
    :meth:`_looks_like_pii` is replaced with :attr:`self.replacement`.
    Lists are traversed index-by-index. The dotted/bracket ``path`` is
    built up as the walk descends and is appended to ``hits`` for each
    redacted leaf, so callers get a flat list of where redaction
    happened.

    Args:
        data: A JSON-compatible Python value (dict / list / scalar).
        hits: Mutable accumulator; matching JSON-pointer-like paths are
            appended here.
        path: Internal recursion cursor used to build ``hits`` entries.
            Pass an empty string at the top level.

    Returns:
        A new structure of the same shape as ``data`` with PII strings
        replaced. Scalars are returned unchanged.
    """
        if isinstance(data, dict):
            cleaned: dict = {}
            for key, value in data.items():
                field_path = f"{path}.{key}" if path else str(key)
                if isinstance(value, str) and self._looks_like_pii(value):
                    hits.append(field_path)
                    cleaned[key] = self.replacement
                else:
                    cleaned[key] = self._redact(value, hits, field_path)
            return cleaned
        if isinstance(data, list):
            return [self._redact(item, hits, f"{path}[{idx}]" if path else f"[{idx}]")
                    for idx, item in enumerate(data)]
        return data

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and redact PII in the response body.

    Invokes ``call_next`` to obtain the downstream response. Skips the
    request entirely when :meth:`_is_allowed` flags the path or route as
    exempt. Otherwise decodes the response body, walks it recursively
    via :meth:`_redact`, and — only when at least one field was actually
    redacted — re-serializes the rewritten body as compact UTF-8 JSON
    and replaces ``response["body"]``. A warning is emitted on the
    configured logger listing the redacted field paths so operators
    can audit where the auto-redaction is firing.

    Args:
        request_data: The in-flight request envelope as carried by the
            middleware chain. The ``path`` and route-name keys are used
            by the allow-list check.
        call_next: Awaitable that invokes the next middleware/handler
            and returns the downstream response dict.

    Returns:
        The downstream response dict, with ``body`` replaced by the
        re-serialized redacted body when redaction occurred. Unchanged
        otherwise (no body rewrite, no warning).
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
            "Auto-redacted PII fields in response",
            extra={"path": path, "redacted_fields": sorted(set(hits))},
        )
        response["body"] = json.dumps(redacted, separators=(",", ":")).encode("utf-8")
        return response


__all__ = ["PIIRedactionMiddleware"]
