"""``rivex.middleware.rate_limit`` — token-bucket rate limiter middleware."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.native._compat import RC_V2, client_ip, get_request_header, json_error_response, rc as _rc
from rivex.middleware.abstraction import IMiddleware


class RateLimitMiddleware(IMiddleware):
    """Token-bucket rate limiter with per-IP, per-user, and global buckets.

    The *strategy* controls which key identifies the client:
    ``"ip"`` (default), ``"user"`` (JWT sub claim), or ``"global"``.

    Multiple instances can be stacked for different limit tiers::

        app.add_middleware(RateLimitMiddleware, rate=100, per=60)
        app.add_middleware(RateLimitMiddleware, rate=1000, per=60, strategy="user")

    Parameters:
        rate:       Number of requests allowed per ``per`` seconds.
        per:        Window size in seconds.
        strategy:   ``"ip"`` | ``"user"`` | ``"global"``.
        key_header: Optional custom header to use as the rate-limit key.
    """

    def __init__(
        self,
        rate: int = 100,
        per: float = 60.0,
        strategy: str = "ip",
        key_header: str | None = None,
    ):
        self.rate = rate
        self.per = per
        self.strategy = strategy
        self.key_header = key_header
        self._is_rust = False
        try:
            if RC_V2 and hasattr(_rc, "TokenBucket"):
                self._buckets: Any = _rc.TokenBucket(rate, per)
                self._is_rust = True
                return
        except Exception:
            pass
        self._buckets: dict[str, list] = {}

    def _key(self, request_data: dict) -> str:
        if self.strategy == "user":
            for k, v in request_data.get("headers", []):
                if k.lower() == Header.AUTHORIZATION:
                    return v
            return "anonymous"
        if self.strategy == "global":
            return "_global"
        if self.key_header:
            val = get_request_header(request_data, self.key_header)
            if val:
                return val
        return client_ip(request_data)

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        key = self._key(request_data)
        if self._is_rust:
            if not self._buckets.check(key):
                resp = json_error_response(HTTPStatus.TOO_MANY_REQUESTS, "Too Many Requests")
                resp["headers"].append(("retry-after", str(int(self.per / self.rate))))
                return resp
        else:
            import time
            now = time.monotonic()
            bucket = self._buckets.setdefault(key, [0.0, self.rate])
            last, tokens = bucket
            tokens = min(self.rate, tokens + (now - last) * (self.rate / self.per))
            if tokens < 1:
                resp = json_error_response(HTTPStatus.TOO_MANY_REQUESTS, "Too Many Requests")
                resp["headers"].append(("retry-after", str(int(self.per / self.rate))))
                return resp
            bucket[0] = now
            bucket[1] = tokens - 1
        return await call_next(request_data)

    def check_batch(self, request_data_list: list[dict]) -> list[bool]:
        """Bulk-check rate limits across many request contexts in one FFI call."""
        if not self._is_rust:
            return [self._check_pure(r) for r in request_data_list]
        keys = [self._key(r) for r in request_data_list]
        return list(self._buckets.check_many(keys))

    def _check_pure(self, request_data: dict) -> bool:
        """Pure-Python fallback for ``check`` semantics (no I/O, no error response)."""
        import time
        key = self._key(request_data)
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, [0.0, self.rate])
        last, tokens = bucket
        tokens = min(self.rate, tokens + (now - last) * (self.rate / self.per))
        if tokens < 1:
            bucket[0] = now
            bucket[1] = tokens
            return False
        bucket[0] = now
        bucket[1] = tokens - 1
        return True


__all__ = ["RateLimitMiddleware"]
