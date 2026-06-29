"""Response caching — middleware and endpoint decorator."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any, overload

from rivex._compat import HAS_CORE, RC_V2, get_request_header
from rivex._compat import rc as _rc
from rivex.middleware import Middleware

try:
    import orjson as _orjson

    def _serialize(obj: Any) -> bytes:
        return _orjson.dumps(obj)
except ImportError:
    import json as _json_mod

    def _serialize(obj: Any) -> bytes:  # type: ignore[misc]
        return _json_mod.dumps(obj).encode("utf-8")


def _md5_etag(body: bytes) -> str:
    if HAS_CORE:
        return f'"{_rc.md5_hex(body)}"'
    import hashlib

    return f'"{hashlib.md5(body).hexdigest()}"'


def _etag_match(etag: str, if_none_match: str) -> bool:
    if RC_V2:
        result: bool = _rc.etag_matches(etag, if_none_match)
        return result
    return if_none_match == etag


class CacheMiddleware(Middleware):
    """In-memory response cache for GET requests with ETag support."""

    def __init__(self, max_age: int = 60, max_entries: int = 1000):
        self.max_age = max_age
        self.max_entries = max_entries
        self._cache: dict[str, tuple[float, dict, str]] = {}

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        method = request_data.get("method", "GET").upper()
        if method != "GET":
            result: dict = await call_next(request_data)
            return result

        cache_key = self._make_key(request_data)

        if cache_key in self._cache:
            ts, cached_response, etag = self._cache[cache_key]
            if time.monotonic() - ts < self.max_age:
                if_none_match = get_request_header(request_data, "if-none-match") or ""
                if _etag_match(etag, if_none_match):
                    return {
                        "status": 304,
                        "headers": [("etag", etag)],
                        "body": b"",
                    }
                response = dict(cached_response)
                headers = list(response.get("headers", []))
                headers.append(("etag", etag))
                headers.append(("x-cache", "HIT"))
                response["headers"] = headers
                return response
            else:
                del self._cache[cache_key]

        response = await call_next(request_data)

        if isinstance(response, dict) and 200 <= response.get("status", 500) < 300:
            body = response.get("body", b"")
            if isinstance(body, bytes):
                etag = _md5_etag(body)
                if len(self._cache) >= self.max_entries:
                    oldest = min(self._cache, key=lambda k: self._cache[k][0])
                    del self._cache[oldest]
                self._cache[cache_key] = (time.monotonic(), response, etag)
                headers = list(response.get("headers", []))
                headers.append(("etag", etag))
                headers.append(("cache-control", f"max-age={self.max_age}"))
                headers.append(("x-cache", "MISS"))
                response["headers"] = headers

        return response

    @staticmethod
    def _make_key(request_data: dict) -> str:
        path = request_data.get("path", "/")
        qs = request_data.get("query_string", "")
        return f"{path}?{qs}" if qs else path


class ETagMiddleware(Middleware):
    """Adds ETag headers and handles If-None-Match for 304 responses."""

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        response: dict = await call_next(request_data)

        if not isinstance(response, dict):
            return response

        status = response.get("status", 200)
        if status != 200:
            return response

        body = response.get("body", b"")
        if not isinstance(body, bytes) or not body:
            return response

        etag = _md5_etag(body)

        if_none_match = get_request_header(request_data, "if-none-match") or ""
        if _etag_match(etag, if_none_match):
            return {
                "status": 304,
                "headers": [("etag", etag)],
                "body": b"",
            }

        headers = list(response.get("headers", []))
        headers.append(("etag", etag))
        response["headers"] = headers
        return response


_JSON_CT = ("content-type", "application/json")
_TEXT_CT = ("content-type", "text/plain; charset=utf-8")


class _CachedWrapper:
    """Wrapper that caches the first response and replays it."""

    def __init__(self, func: Callable, ttl: float | None):
        self._func = func
        self._ttl = ttl
        self._cached_response: dict | None = None
        self._cached_at: float = 0
        self._is_async = asyncio.iscoroutinefunction(func)
        self.__name__ = getattr(func, "__name__", "cached")
        self.__module__ = getattr(func, "__module__", "")
        self.__qualname__ = getattr(func, "__qualname__", "")
        self.__doc__ = func.__doc__
        self.__wrapped__ = func
        self.__annotations__ = getattr(func, "__annotations__", {})

    def _is_stale(self) -> bool:
        if self._cached_response is None:
            return True
        if self._ttl is not None and (time.monotonic() - self._cached_at) > self._ttl:
            return True
        return False

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if not self._is_stale():
            return self._cached_response

        if self._is_async:
            result = await self._func(*args, **kwargs)
        else:
            result = self._func(*args, **kwargs)

        if isinstance(result, dict) or isinstance(result, list):
            self._cached_response = {
                "status": 200,
                "headers": [_JSON_CT],
                "body": _serialize(result),
            }
        elif isinstance(result, str):
            self._cached_response = {
                "status": 200,
                "headers": [_TEXT_CT],
                "body": result.encode("utf-8"),
            }
        elif isinstance(result, bytes):
            self._cached_response = {
                "status": 200,
                "headers": [("content-type", "application/octet-stream")],
                "body": result,
            }
        else:
            return result

        self._cached_at = time.monotonic()
        return self._cached_response

    def __call_baked__(self) -> dict[str, Any] | None:
        """Bake the response once and return the cached form.

        Used by the Rust-side auto-bake optimisation in
        ``applications._drive_rust_server``. We synchronously call
        the user function (or schedule it on a fresh event loop if
        it's async), capture the response, and return it. The Rust
        side then registers the response as a const-route so future
        requests bypass Python entirely.

        Returns the cached response dict, or ``None`` if the handler
        depends on the request (e.g. reads ``request.path_params``)
        and so can't be pre-baked.
        """
        if self._cached_response is not None:
            return self._cached_response

        try:
            if self._is_async:
                # Bake the async handler on a fresh, ephemeral
                # event loop so we don't disturb the running app.
                import asyncio as _aio

                try:
                    loop = _aio.get_event_loop()
                    if loop.is_running():
                        # We can't share the loop — create a new one.
                        raise RuntimeError("busy loop")
                    baked = loop.run_until_complete(self._func())
                except RuntimeError:
                    # Use a one-shot loop in a fresh thread context.
                    # In practice this never happens at registration
                    # time, but be defensive.
                    new_loop = _aio.new_event_loop()
                    try:
                        baked = new_loop.run_until_complete(self._func())
                    finally:
                        new_loop.close()
            else:
                baked = self._func()

            if isinstance(baked, dict) or isinstance(baked, list):
                self._cached_response = {
                    "status": 200,
                    "headers": [_JSON_CT],
                    "body": _serialize(baked),
                }
            elif isinstance(baked, str):
                self._cached_response = {
                    "status": 200,
                    "headers": [_TEXT_CT],
                    "body": baked.encode("utf-8"),
                }
            elif isinstance(baked, bytes):
                self._cached_response = {
                    "status": 200,
                    "headers": [("content-type", "application/octet-stream")],
                    "body": baked,
                }
            else:
                return None

            self._cached_at = time.monotonic()
            return self._cached_response
        except Exception:
            return None

    def cache_clear(self) -> None:
        self._cached_response = None
        self._cached_at = 0


@overload
def cached_response(func: Callable) -> _CachedWrapper: ...


@overload
def cached_response(*, ttl: float | None = None) -> Callable[[Callable], _CachedWrapper]: ...


def cached_response(func: Callable | None = None, *, ttl: float | None = None):
    """Cache the response of a deterministic endpoint."""
    if func is not None:
        return _CachedWrapper(func, ttl=None)

    def decorator(fn: Callable) -> _CachedWrapper:
        return _CachedWrapper(fn, ttl=ttl)

    return decorator
