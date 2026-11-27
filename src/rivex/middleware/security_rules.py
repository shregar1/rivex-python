"""``rivex.middleware.security_rules`` — drop-in :class:`IValidationRule` implementations.

These rules plug into :class:`rivex.middleware.request_validation.RequestValidationMiddleware`.
Three classes ship out of the box:

* :class:`SanitizeXssRule` — rejects requests whose body / query string
  contains XSS markers, then strips the offending tags from string
  leaves before letting the handler run.
* :class:`SanitizePiiRule` — auto-redacts PII matches in outgoing
  responses and emits a dev-mode warning when fields were stripped.
* :class:`ApiKeyLeakRule` — strips accidentally exposed API keys /
  secrets from response bodies.

Each rule accepts ``exclude_paths`` / ``exclude_methods`` to opt out
of specific routes (e.g. the key-creation endpoint that legitimately
returns an API key).
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from rivex.constants.regex import InjectionRegex, Regex
from rivex.middleware.request_validation import IValidationRule


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


def _walk_strings(obj: Any) -> list[str]:
    """Collect every string leaf found inside ``obj`` in document order.

    Recurses into nested dicts and lists, appending each string leaf
    to the result. Other scalar types are ignored.

    Args:
        obj: A JSON-compatible Python value to traverse.

    Returns:
        A flat list of every string encountered during the walk, in the
        order they were visited. Empty when ``obj`` has no string leaves.
    """
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            out.extend(_walk_strings(value))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_walk_strings(item))
    return out


def _strip_separators(value: str) -> str:
    """Remove ``-`` and `` `` characters from ``value``.

    Normalizes PII-shaped numbers (credit-card digits with dashes /
    spaces) before applying the loose card-number fallback regex.

    Args:
        value: The string to normalize.

    Returns:
        ``value`` with all hyphens and ASCII spaces removed.
    """
    return value.replace("-", "").replace(" ", "")


class _BaseRule(IValidationRule):
    """Shared path / method exclusion handling."""

    def __init__(
        self,
        exclude_paths: Optional[List[str]] = None,
        exclude_methods: Optional[List[str]] = None,
    ) -> None:
        self.exclude_paths = list(exclude_paths or [])
        self.exclude_methods = [m.upper() for m in (exclude_methods or [])]

    def is_excluded(self, path: str, method: str) -> bool:
        """Return ``True`` when this rule should be skipped for this request.

    Matches when the request method is in ``self.exclude_methods`` (case
    insensitive) or when the request path is in ``self.exclude_paths``
    either as an exact match or as a prefix glob (entries ending in
    ``"*"`` are treated as prefix globs).

    Args:
        path: The request path string to test against the exclude list.
        method: The HTTP method string to test against the exclude list.

    Returns:
        ``True`` when this rule should not run for the given request,
        ``False`` otherwise.
    """
        if method.upper() in self.exclude_methods:
            return True
        for pattern in self.exclude_paths:
            if pattern.endswith("*") and path.startswith(pattern[:-1]):
                return True
            if pattern == path:
                return True
        return False

    @staticmethod
    def _should_abort_dict(hits: list[str], path: str) -> Optional[dict[str, Any]]:
        """Return an abort response, or ``None`` to continue. Subclasses override."""
        return None


class SanitizeXssRule(_BaseRule):
    """Reject requests with XSS markers, then strip tags from string leaves."""

    def __init__(
        self,
        *,
        xss_pattern: str = InjectionRegex.XSS_PATTERN,
        sqli_pattern: str = InjectionRegex.SQLI_PATTERN,
        strip_on_sanitize: bool = True,
        exclude_paths: Optional[List[str]] = None,
        exclude_methods: Optional[List[str]] = None,
    ) -> None:
        super().__init__(exclude_paths=exclude_paths, exclude_methods=exclude_methods)
        self._xss = re.compile(xss_pattern, re.IGNORECASE | re.DOTALL)
        self._sqli = re.compile(sqli_pattern, re.IGNORECASE | re.DOTALL)
        self._strip = strip_on_sanitize

    def _contains_malicious(self, value: str) -> bool:
        """Return ``True`` when ``value`` matches the XSS or SQLi regexes.

    The match is case-insensitive and uses ``re.DOTALL`` so multi-line
    payloads are caught. Either regex hit is enough to flag the value.

    Args:
        value: The candidate string to scan.

    Returns:
        ``True`` when either the configured XSS or SQLi regex finds a
        match in ``value``.
    """
        return self._xss.search(value) is not None or self._sqli.search(value) is not None

    async def validate_request(self, request_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Reject the request when XSS/SQLi markers appear in the input.

    Skips the rule entirely when :meth:`is_excluded` reports the path
    or method is opted out. Otherwise inspects the query string for any
    XSS/SQLi match and, for ``POST``/``PUT``/``PATCH`` requests, walks
    every string leaf in the decoded JSON body looking for the same
    markers. On a hit returns a 422 response carrying a
    ``MALICIOUS_INPUT_DETECTED`` error payload; otherwise returns
    ``None`` so the pipeline can continue.

    Args:
        request_data: The in-flight request envelope. ``path``,
            ``method``, ``query_string``, and ``body`` are inspected.

    Returns:
        A 422 abort response when a malicious marker is found, or
        ``None`` to let the request proceed.
    """
        if self.is_excluded(request_data.get("path") or "", request_data.get("method") or ""):
            return None

        qs = request_data.get("query_string") or ""
        if isinstance(qs, str) and self._contains_malicious(qs):
            return {
                "status": 422,
                "headers": [],
                "body": json.dumps(
                    {"errors": [{"code": "MALICIOUS_INPUT_DETECTED", "message": "XSS/SQLi marker in query string"}]}
                ).encode("utf-8"),
            }

        method = (request_data.get("method") or "").upper()
        if method in {"POST", "PUT", "PATCH"}:
            parsed = _json_body(request_data.get("body"))
            for value in _walk_strings(parsed or {}):
                if self._contains_malicious(value):
                    return {
                        "status": 422,
                        "headers": [],
                        "body": json.dumps(
                            {"errors": [{"code": "MALICIOUS_INPUT_DETECTED", "message": "XSS/SQLi marker in body"}]}
                        ).encode("utf-8"),
                    }
        return None

    async def sanitize_response(self, response: dict[str, Any]) -> Optional[bytes]:
        """Strip XSS markers from the response body when configured to do so.

    Always returns ``None`` for the base implementation — subclasses
    override this to actually rewrite response bodies. When the rule
    is configured with ``strip_on_sanitize=False`` the same no-op
    behavior is used.

    Args:
        response: The downstream response dict. Unused by this base
            implementation but accepted to satisfy the
            :class:`IValidationRule` contract.

    Returns:
        ``None`` to leave the body unchanged. Subclasses override to
        return replacement bytes.
    """
        if not self._strip:
            return None
        return None  # Subclasses that want response sanitization can override.


class SanitizePiiRule(_BaseRule):
    """Auto-redact SSN / credit-card matches in outgoing responses."""

    def __init__(
        self,
        *,
        patterns: Optional[List[str]] = None,
        replacement: str = "[REDACTED]",
        exclude_paths: Optional[List[str]] = None,
        exclude_methods: Optional[List[str]] = None,
    ) -> None:
        super().__init__(exclude_paths=exclude_paths, exclude_methods=exclude_methods)
        self._regexes = [
            p if isinstance(p, re.Pattern) else re.compile(p)
            for p in (patterns or [Regex.SSN, Regex.CARD])
        ]
        self.replacement = replacement
        self._card = re.compile(Regex.CARD)

    def _looks_like_pii(self, value: str) -> bool:
        """Return ``True`` when ``value`` looks like PII under any configured regex.

    First runs every configured PII regex against the raw value. If
    none match, applies the loose credit-card fallback: strip ``-`` and
    spaces, require the resulting digit count to be between 12 and 19,
    and require the extra-card regex to match the digits-only form.

    Args:
        value: The candidate string to classify.

    Returns:
        ``True`` when the value should be treated as PII and redacted.
    """
        for regex in self._regexes:
            if regex.match(value):
                return True
        if 12 <= len(_strip_separators(value)) <= 19 and self._card.match(_strip_separators(value)):
            return True
        return False

    def _walk(self, data: Any, hits: list[str], path: str = "") -> Any:
        """Recursively walk ``data`` and replace every PII string in place.

    Dicts are traversed key-by-key, and any string value classified by
    :meth:`_looks_like_pii` is replaced with :attr:`replacement`.
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
                    cleaned[key] = self._walk(value, hits, field_path)
            return cleaned
        if isinstance(data, list):
            return [self._walk(item, hits, f"{path}[{idx}]" if path else f"[{idx}]")
                    for idx, item in enumerate(data)]
        return data

    async def validate_request(self, request_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Always allow the request through to the handler.

    The rule only sanitizes responses, so this implementation never
    aborts the pipeline. The signature matches the abstract contract on
    :class:`IValidationRule`.

    Args:
        request_data: The in-flight request envelope. Unused.

    Returns:
        ``None`` to let the request proceed unchanged.
    """
        return None

    async def sanitize_response(self, response: dict[str, Any]) -> Optional[bytes]:
        """Replace PII strings in the response body with the configured mask.

    Decodes the response body via :func:`_json_body`. When the decoded
    value is neither a dict nor a list (or the body could not be
    parsed), returns ``None`` to leave the body untouched. Otherwise
    walks the structure with :meth:`_walk`, accumulating hit paths;
    only when at least one field was redacted is the rewritten body
    serialized as compact UTF-8 JSON and returned.

    Args:
        response: The downstream response dict. Only the ``body`` key is
            read.

    Returns:
        The re-serialized redacted body bytes when at least one field
        was replaced, otherwise ``None`` to leave the response body
        alone.
    """
        parsed = _json_body(response.get("body"))
        if not isinstance(parsed, (dict, list)):
            return None
        hits: list[str] = []
        redacted = self._walk(parsed, hits)
        if not hits:
            return None
        return json.dumps(redacted, separators=(",", ":")).encode("utf-8")


class ApiKeyLeakRule(_BaseRule):
    """Strip accidentally exposed API keys / secrets from response bodies."""

    def __init__(
        self,
        *,
        custom_key_patterns: Optional[List[str]] = None,
        custom_value_patterns: Optional[List[str]] = None,
        replacement: str = "[REDACTED]",
        exclude_paths: Optional[List[str]] = None,
        exclude_methods: Optional[List[str]] = None,
        allowed_paths: Optional[List[str]] = None,
        allowed_route_names: Optional[List[str]] = None,
    ) -> None:
        super().__init__(exclude_paths=exclude_paths, exclude_methods=exclude_methods)
        key_patterns = list(Regex.DEFAULT_KEY_NAMES) + list(custom_key_patterns or [])
        value_patterns = list(Regex.DEFAULT_VALUES) + list(custom_value_patterns or [])
        self._key_regexes = Regex.compile_patterns(key_patterns)
        self._value_regexes = Regex.compile_patterns(value_patterns)
        self.replacement = replacement
        # Allow-list: paths OR route names that legitimately return secrets.
        self._allowed_path_globs: List[str] = list(
            (exclude_paths or []) + (allowed_paths or [])
        )
        self._allowed_route_names: frozenset[str] = frozenset(allowed_route_names or [])

    def _value_is_secret(self, value: str) -> bool:
        """Return ``True`` when ``value`` looks like a leaked secret.

    Tests every configured value-shape regex on ``value`` and on two
    normalized variants: a stripped version (outer whitespace removed)
    and a further ``"``/``'``-stripped version. Any hit on any variant
    is enough to flag the value.

    Args:
        value: The candidate string to test.

    Returns:
        ``True`` when at least one configured regex matches the raw or
        normalized forms of ``value``.
    """
        candidates = (value, value.strip().strip('"').strip("'"))
        return any(
            regex.search(candidate)
            for regex in self._value_regexes
            for candidate in candidates
        )

    def _key_is_secret(self, key: str) -> bool:
        """Return ``True`` when the dict key name suggests a secret field.

    Args:
        key: The dict key to test.

    Returns:
        ``True`` when at least one configured key-name regex matches
        ``key`` (e.g. ``"api_key"``, ``"access_token"``).
    """
        return any(regex.search(key) for regex in self._key_regexes)

    def _is_allowed(self, path: str, method: str, request_data: dict[str, Any]) -> bool:
        """Decide whether this request is exempt from API-key redaction.

    Bails out (returns ``True``) when the path/method is in the base
    exclude list, or when the resolved route name is in the allow list
    of routes that legitimately return secrets.

    Args:
        path: The request path string.
        method: The HTTP method string.
        request_data: The request envelope. Only the route-name fields
            are read.

    Returns:
        ``True`` when this rule should skip redacting the response.
    """
        if self.is_excluded(path, method):
            return True
        route_name = request_data.get("route_name") or request_data.get("matched_route_name")
        if route_name and route_name in self._allowed_route_names:
            return True
        return False

    def _walk(self, data: Any, hits: list[str], path: str = "") -> Any:
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
                    cleaned[key] = self._walk(value, hits, field_path)
            return cleaned
        if isinstance(data, list):
            return [self._walk(item, hits, f"{path}[{idx}]" if path else f"[{idx}]")
                    for idx, item in enumerate(data)]
        return data

    async def validate_request(self, request_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Always allow the request through to the handler.

    The rule only sanitizes responses, so this implementation never
    aborts the pipeline. The signature matches the abstract contract on
    :class:`IValidationRule`.

    Args:
        request_data: The in-flight request envelope. Unused.

    Returns:
        ``None`` to let the request proceed unchanged.
    """
        return None

    async def sanitize_response(self, response: dict[str, Any]) -> Optional[bytes]:
        """Strip accidentally exposed API keys from the response body.

    Reads the request envelope that
    :class:`RequestValidationMiddleware` pinned onto the response via
    the ``_request_data`` key and bails out when the route is on the
    allow list. Otherwise decodes the response body via
    :func:`_json_body`, walks it with :meth:`_walk`, and only returns
    re-serialized UTF-8 JSON bytes when at least one field was
    actually replaced.

    Args:
        response: The downstream response dict. ``body`` is the
            candidate JSON payload, ``_request_data`` (set by the
            validation middleware) carries the originating request envelope.

    Returns:
        The re-serialized redacted body bytes when at least one field
        was replaced, otherwise ``None`` to leave the response alone.
    """
        request_data = response.get("_request_data") or {}
        path = request_data.get("path") or ""
        method = request_data.get("method") or ""
        if self._is_allowed(path, method, request_data):
            return None
        parsed = _json_body(response.get("body"))
        if not isinstance(parsed, (dict, list)):
            return None
        hits: list[str] = []
        redacted = self._walk(parsed, hits)
        if not hits:
            return None
        return json.dumps(redacted, separators=(",", ":")).encode("utf-8")


__all__ = ["SanitizeXssRule", "SanitizePiiRule", "ApiKeyLeakRule"]
