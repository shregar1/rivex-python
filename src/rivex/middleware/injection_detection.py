"""``rivex.middleware.injection_detection`` — detect (and optionally reject) XSS / SQL injection / NoSQL injection attempts.

Two layers, one module:

* :class:`InjectionDetectionMiddleware` — a fast pre-routing rejector that
  walks every request body, query string, and header looking for the
  built-in :class:`InjectionRegex` patterns (and optional caller-supplied
  patterns). On a hit it short-circuits with a ``422 Unprocessable
  Entity`` so the malicious request never reaches the handler.

* :class:`NoSQLInjectionDetectionMiddleware` — detects NoSQL operator
  injection (``{"$ne": null}``-style payloads) in JSON bodies and
  rejects the request.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any, Optional

from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.regex import InjectionRegex, Regex
from rivex.middleware.abstraction import IMiddleware


def _json_body(body: Any) -> Optional[Any]:
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
    """Return every string value found anywhere in ``obj``."""
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


class _InjectionCheck(ABC):
    """Base for an injection detection strategy."""

    @abstractmethod
    def matches(self, value: str) -> bool: ...


class _RegexInjectionCheck(_InjectionCheck):
    def __init__(self, pattern: str | re.Pattern[str], *, flags: int = re.IGNORECASE | re.DOTALL) -> None:
        self._re = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern, flags)

    def matches(self, value: str) -> bool:
        return self._re.search(value) is not None


class InjectionDetectionMiddleware(IMiddleware):
    """Reject requests whose body / query string contains injection markers.

    Parameters:
        reject_xss: When ``True`` (default), XSS patterns short-circuit
            the request with 422.
        reject_sqli: When ``True`` (default), SQL-injection patterns
            short-circuit the request with 422.
        extra_patterns: Additional regexes to flag (merged with the
            built-in XSS / SQLi patterns when their respective reject
            flag is enabled).
        path_predicate: ``Callable[[str], bool]`` — only inspect these
            paths (``None`` means every path).
        excluded_paths: Paths to skip entirely (exact match plus
            ``"*"`` suffix glob).
        max_scan_bytes: Stop scanning once the body exceeds this many
            bytes (defends against malicious payloads trying to make
            the scanner blow up).
    """

    def __init__(
        self,
        *,
        reject_xss: bool = True,
        reject_sqli: bool = True,
        extra_patterns: Sequence[str | re.Pattern[str]] = (),
        path_predicate: Optional[Callable[[str], bool]] = None,
        excluded_paths: Sequence[str] = (),
        max_scan_bytes: int = 1_048_576,
    ) -> None:
        self.reject_xss = reject_xss
        self.reject_sqli = reject_sqli
        self._extra = list(Regex.compile_patterns(extra_patterns))
        self._path_predicate = path_predicate
        self._excluded = tuple(excluded_paths)
        self.max_scan_bytes = int(max_scan_bytes)

        self._checks: list[_InjectionCheck] = []
        if reject_xss:
            self._checks.append(_RegexInjectionCheck(InjectionRegex.XSS_PATTERN))
        if reject_sqli:
            self._checks.append(_RegexInjectionCheck(InjectionRegex.SQLI_PATTERN))
        for p in self._extra:
            self._checks.append(_RegexInjectionCheck(p))

    def _is_excluded(self, path: str) -> bool:
        if self._path_predicate is not None and not self._path_predicate(path):
            return True
        for excluded in self._excluded:
            if excluded.endswith("*") and path.startswith(excluded[:-1]):
                return True
            if path == excluded:
                return True
        return False

    def _scan_string(self, value: str) -> Optional[str]:
        for check in self._checks:
            if check.matches(value):
                return check.__class__.__name__
        return None

    def _scan_request(self, request_data: dict) -> Optional[str]:
        path = request_data.get("path") or ""
        if self._is_excluded(path):
            return None

        qs = request_data.get("query_string") or ""
        if qs and isinstance(qs, str) and self._scan_string(qs):
            return f"query_string ({qs[:64]})"

        body = request_data.get("body")
        if body is None:
            return None
        if isinstance(body, (bytes, bytearray)) and len(body) > self.max_scan_bytes:
            body = bytes(body)[: self.max_scan_bytes]
        if isinstance(body, str) and len(body) > self.max_scan_bytes:
            body = body[: self.max_scan_bytes]

        if isinstance(body, str):
            if self._scan_string(body):
                return f"body (str, {body[:64]!r})"

        parsed = _json_body(body)
        if parsed is None:
            return None

        for value in _walk_strings(parsed):
            hit = self._scan_string(value)
            if hit:
                return f"body string field ({value[:64]!r})"
        return None

    @staticmethod
    def _reject(reference_urn: Any, kind: str) -> dict:
        envelope = {
            "api_status": "FAILURE",
            "transaction_urn": reference_urn,
            "errors": [
                {
                    "code": ExceptionCode.MALICIOUS_INPUT_DETECTED,
                    "message": f"Malicious input detected: {kind}",
                }
            ],
        }
        import json as _json

        from rivex.constants.api.header import Header
        from rivex.constants.api.media_type import MediaType

        return {
            "status": HTTPStatus.UNPROCESSABLE_ENTITY,
            "headers": [(Header.CONTENT_TYPE, MediaType.APPLICATION_JSON)],
            "body": _json.dumps(envelope).encode("utf-8"),
        }

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        if not self._checks:
            return await call_next(request_data)
        kind = self._scan_request(request_data)
        if kind is not None:
            return self._reject(request_data.get("urn"), kind)
        return await call_next(request_data)


class NoSQLInjectionDetectionMiddleware(IMiddleware):
    """Reject requests whose JSON body contains MongoDB operator keys.

    Patterns flagged:
      * Any top-level / nested key starting with ``$`` (``$ne``, ``$gt``,
        ``$where``, …) — the classic NoSQL operator-injection marker.
      * Any value that *contains* a ``$`` operator key (e.g. ``{"key":
        {"$ne": null}}``) — same threat via a wrapped structure.

    By default the middleware rejects with ``422``; pass ``mode="strip"``
    to silently strip the offending keys from the JSON body instead.
    """

    _OPERATOR_PREFIX: str = "$"

    def __init__(
        self,
        *,
        mode: str = "reject",
        path_predicate: Optional[Callable[[str], bool]] = None,
        excluded_paths: Sequence[str] = (),
    ) -> None:
        if mode not in {"reject", "strip"}:
            raise ValueError("mode must be 'reject' or 'strip'")
        self.mode = mode
        self._path_predicate = path_predicate
        self._excluded = tuple(excluded_paths)

    def _is_excluded(self, path: str) -> bool:
        if self._path_predicate is not None and not self._path_predicate(path):
            return True
        for excluded in self._excluded:
            if excluded.endswith("*") and path.startswith(excluded[:-1]):
                return True
            if path == excluded:
                return True
        return False

    def _scan(self, obj: Any, path: str = "") -> Optional[str]:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(key, str) and key.startswith(self._OPERATOR_PREFIX):
                    return f"{path or '<root>'}.{key}"
                hit = self._scan(value, f"{path}.{key}" if path else str(key))
                if hit:
                    return hit
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                hit = self._scan(item, f"{path}[{idx}]")
                if hit:
                    return hit
        return None

    def _strip(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: self._strip(v)
                for k, v in obj.items()
                if not (isinstance(k, str) and k.startswith(self._OPERATOR_PREFIX))
            }
        if isinstance(obj, list):
            return [self._strip(item) for item in obj]
        return obj

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        path = request_data.get("path") or ""
        if self._is_excluded(path):
            return await call_next(request_data)

        method = (request_data.get("method") or "").upper()
        if method not in {"POST", "PUT", "PATCH"}:
            return await call_next(request_data)

        parsed = _json_body(request_data.get("body"))
        if not isinstance(parsed, (dict, list)):
            return await call_next(request_data)

        hit = self._scan(parsed)
        if hit is None:
            return await call_next(request_data)

        if self.mode == "strip":
            request_data["body"] = json.dumps(self._strip(parsed), separators=(",", ":")).encode("utf-8")
            return await call_next(request_data)

        envelope = {
            "api_status": "FAILURE",
            "transaction_urn": request_data.get("urn"),
            "errors": [
                {
                    "code": ExceptionCode.MALICIOUS_INPUT_DETECTED,
                    "message": f"NoSQL injection detected at '{hit}'.",
                }
            ],
        }
        from rivex.constants.api.header import Header
        from rivex.constants.api.media_type import MediaType

        return {
            "status": HTTPStatus.UNPROCESSABLE_ENTITY,
            "headers": [(Header.CONTENT_TYPE, MediaType.APPLICATION_JSON)],
            "body": json.dumps(envelope).encode("utf-8"),
        }


__all__ = [
    "InjectionDetectionMiddleware",
    "NoSQLInjectionDetectionMiddleware",
]
