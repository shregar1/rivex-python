"""``rivex.middleware.idempotency`` — Stripe-style idempotency key middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.header import Header
from rivex.constants.api.http_method import HTTPMethod
from rivex.native._compat import get_request_header
from rivex.middleware.abstraction import IMiddleware


class IdempotencyMiddleware(IMiddleware):
    """Stripe-style idempotency key support for safe retries.

    Caches the response for ``POST``, ``PUT``, and ``PATCH`` requests that
    carry an ``Idempotency-Key`` header. Subsequent requests with the same
    key (within ``ttl`` seconds) receive the cached response without
    re-executing the handler.

    Parameters:
        header_name: Request header carrying the idempotency key.
        ttl:         Cache time-to-live in seconds (default 24 h).
        max_entries: Maximum number of cached responses (oldest are evicted).
    """

    def __init__(
        self,
        header_name: str = Header.IDEMPOTENCY_KEY,
        ttl: float = 86400.0,
        max_entries: int = 10000,
    ):
        self.header_name = header_name
        self.ttl = ttl
        self.max_entries = max_entries
        self._cache: dict[str, tuple[float, dict]] = {}

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and short-circuit repeated mutating requests.

        Non-mutating methods (``GET``/``HEAD``/``DELETE``/``OPTIONS``) and
        mutating requests without the configured ``Idempotency-Key`` header
        are forwarded to ``call_next`` unchanged. For mutating requests
        with a key, a cached response is returned if one is still within
        :attr:`ttl`; otherwise the request is forwarded and the resulting
        response is cached. After each forward, the cache is opportunistically
        swept for entries older than :attr:`ttl` when :attr:`max_entries`
        is exceeded.

        Args:
            request_data: The in-flight request envelope. ``method`` and
                the configured ``Idempotency-Key`` header are read.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            Either a previously cached response (when the same key was
            seen within the TTL), or the downstream response produced by
            ``call_next`` (now cached for future replays).
        """
        import time

        method = request_data.get("method", "").upper()
        if method not in (HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH):
            return await call_next(request_data)

        key = get_request_header(request_data, self.header_name)
        if key is None:
            return await call_next(request_data)

        now = time.monotonic()

        if key in self._cache:
            ts, cached_response = self._cache[key]
            if now - ts < self.ttl:
                return cached_response

        response: dict = await call_next(request_data)
        self._cache[key] = (now, response)

        if len(self._cache) > self.max_entries:
            expired = [k for k, (ts, _) in self._cache.items() if now - ts >= self.ttl]
            for k in expired:
                del self._cache[k]

        return response


__all__ = ["IdempotencyMiddleware"]
