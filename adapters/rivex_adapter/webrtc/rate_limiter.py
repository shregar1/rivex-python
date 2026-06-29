"""
Per-peer and per-method rate limiting for WebRTC data channels.

Supports:
- Token bucket and sliding window algorithms
- Per-peer, per-method, and global rate limits
- Async-aware (await when tokens are available)

Usage::

    limiter = RateLimiter()

    # Limit peer "alice" to 10 messages per second
    limiter.limit_peer("alice", max_rate=10, window=1.0)

    # Limit the "chat.send" method to 5 calls per 10 seconds
    limiter.limit_method("chat.send", max_rate=5, window=10.0)

    # Check before handling
    if await limiter.check("alice", "chat.send"):
        # handle message
        await limiter.consume("alice", "chat.send")
    else:
        # rate limited
        pass

    # Or use the async context manager
    async with limiter.acquire("alice", "chat.send"):
        # handle message
        pass
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RateLimitRule:
    """A rate limit rule.

    Attributes:
        max_rate: Maximum number of tokens/requests allowed.
        window: Time window in seconds.
        algorithm: "token_bucket" or "sliding_window".
    """

    max_rate: float
    window: float = 1.0
    algorithm: str = "token_bucket"


class TokenBucket:
    """Token bucket rate limiter."""

    def __init__(self, max_rate: float, window: float = 1.0):
        self._capacity = max_rate
        self._tokens = max_rate
        self._refill_rate = max_rate / window
        self._last_refill = time.time()

    async def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        """Try to acquire tokens, waiting if needed."""
        deadline = time.time() + timeout if timeout else float("inf")
        while time.time() < deadline:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            await asyncio.sleep(0.01)
        return False

    def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without blocking."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now


class SlidingWindow:
    """Sliding window log rate limiter."""

    def __init__(self, max_rate: float, window: float = 1.0):
        self._max_rate = max_rate
        self._window = window
        self._timestamps: list[float] = []

    def try_acquire(self) -> bool:
        now = time.time()
        cutoff = now - self._window
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        if len(self._timestamps) < self._max_rate:
            self._timestamps.append(now)
            return True
        return False


class RateLimiterEntry:
    """Tracks rate limits for a single scope (peer or method)."""

    def __init__(self):
        self._buckets: dict[str, TokenBucket | SlidingWindow] = {}
        self._rules: list[RateLimitRule] = []

    def add_rule(self, rule: RateLimitRule) -> None:
        self._rules.append(rule)
        key = f"{rule.algorithm}:{rule.max_rate}:{rule.window}"
        if rule.algorithm == "token_bucket":
            self._buckets[key] = TokenBucket(rule.max_rate, rule.window)
        else:
            self._buckets[key] = SlidingWindow(rule.max_rate, rule.window)

    async def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        for bucket in self._buckets.values():
            if isinstance(bucket, TokenBucket):
                ok = await bucket.acquire(tokens, timeout)
            else:
                ok = bucket.try_acquire()
            if not ok:
                return False
        return True

    def try_acquire(self, tokens: int = 1) -> bool:
        for bucket in self._buckets.values():
            if isinstance(bucket, TokenBucket):
                ok = bucket.try_acquire(tokens)
            else:
                ok = bucket.try_acquire()
            if not ok:
                return False
        return True


class RateLimiter:
    """Hierarchical rate limiter for WebRTC conference messaging.

    Checks are evaluated in order:
      1. Global limits
      2. Per-method limits
      3. Per-peer limits

    All must pass for the request to be allowed.

    Usage::

        limiter = RateLimiter()

        # 10 messages/second globally
        limiter.limit_global(max_rate=10, window=1.0)

        # 5 chat.sends per 10 seconds per peer
        limiter.limit_method("chat.send", max_rate=5, window=10.0)

        # 2 screen shares per minute per peer
        limiter.limit_peer("alice", max_rate=2, window=60.0)

        async with limiter.acquire("alice", "chat.send"):
            do_work()
    """

    def __init__(self):
        self._global = RateLimiterEntry()
        self._methods: dict[str, RateLimiterEntry] = {}
        self._peers: dict[str, RateLimiterEntry] = {}

    def limit_global(
        self, max_rate: float, window: float = 1.0, algorithm: str = "token_bucket"
    ) -> None:
        """Set a global rate limit."""
        self._global.add_rule(RateLimitRule(max_rate, window, algorithm))

    def limit_method(
        self, method: str, max_rate: float, window: float = 1.0, algorithm: str = "token_bucket"
    ) -> None:
        """Set a rate limit for a specific method."""
        if method not in self._methods:
            self._methods[method] = RateLimiterEntry()
        self._methods[method].add_rule(RateLimitRule(max_rate, window, algorithm))

    def limit_peer(
        self, peer_id: str, max_rate: float, window: float = 1.0, algorithm: str = "token_bucket"
    ) -> None:
        """Set a rate limit for a specific peer."""
        if peer_id not in self._peers:
            self._peers[peer_id] = RateLimiterEntry()
        self._peers[peer_id].add_rule(RateLimitRule(max_rate, window, algorithm))

    async def acquire(
        self, peer_id: str, method: str, tokens: int = 1, timeout: float | None = None
    ) -> bool:
        """Acquire permission to process a message.

        Checks global → method → peer limits.

        Returns:
            ``True`` if allowed, ``False`` if rate-limited.
        """
        if not await self._global.acquire(tokens, timeout):
            return False
        if method in self._methods:
            if not await self._methods[method].acquire(tokens, timeout):
                return False
        if peer_id in self._peers:
            if not await self._peers[peer_id].acquire(tokens, timeout):
                return False
        return True

    def try_acquire(self, peer_id: str, method: str, tokens: int = 1) -> bool:
        """Non-blocking check."""
        return (
            self._global.try_acquire(tokens)
            and self._methods.get(method, RateLimiterEntry()).try_acquire(tokens)
            and self._peers.get(peer_id, RateLimiterEntry()).try_acquire(tokens)
        )

    def reset(self) -> None:
        """Clear all limits and entries."""
        self._global = RateLimiterEntry()
        self._methods.clear()
        self._peers.clear()


__all__ = [
    "RateLimiter",
    "RateLimitRule",
    "TokenBucket",
    "SlidingWindow",
]
