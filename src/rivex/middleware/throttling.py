from __future__ import annotations

import time

from rivex.core._compat import client_ip, get_request_header, json_error_response
from rivex.middleware.middleware import Middleware


class BaseThrottle:
    """Base throttle class. Subclass and set `rate`."""

    scope: str = "default"
    rate: str | None = None  # e.g., "100/hour", "10/minute"

    def __init__(self):
        self._cache: dict[str, list[float]] = {}  # key -> list of timestamps

    def parse_rate(self) -> tuple[int, float] | None:
        """Parse rate string like '100/hour' to (100, 3600.0)."""
        if not self.rate:
            return None
        num, period = self.rate.split("/")
        durations = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
        # Also support shorthand: s, m, h, d
        duration = durations.get(period) or durations.get(
            {"s": "second", "m": "minute", "h": "hour", "d": "day"}.get(period, ""), 1
        )
        return int(num), float(duration)

    def get_ident(self, request_data: dict) -> str:
        """Return unique identifier for the requester."""
        return client_ip(request_data)

    def allow_request(self, request_data: dict) -> bool:
        """Check if request is allowed. Uses sliding window."""
        parsed = self.parse_rate()
        if not parsed:
            return True
        max_requests, duration = parsed
        key = f"{self.scope}:{self.get_ident(request_data)}"
        now = time.monotonic()
        # Get timestamps, filter out expired
        history = self._cache.get(key, [])
        history = [t for t in history if now - t < duration]
        if len(history) >= max_requests:
            self._cache[key] = history
            return False
        history.append(now)
        self._cache[key] = history
        return True

    def wait(self) -> float | None:
        """Seconds until next request would be allowed."""
        # Calculate from the oldest entry in the window
        ...


class AnonRateThrottle(BaseThrottle):
    """Rate limit unauthenticated requests by IP."""

    scope = "anon"
    rate = "100/hour"


class UserRateThrottle(BaseThrottle):
    """Rate limit authenticated requests by user identifier."""

    scope = "user"
    rate = "1000/hour"

    def get_ident(self, request_data):
        return get_request_header(request_data, "x-user-id") or super().get_ident(request_data)


class ScopedRateThrottle(BaseThrottle):
    """Rate limit by custom scope. Set scope_rates dict to configure."""

    scope_rates: dict[str, str] = {}  # {"uploads": "10/minute", "search": "30/minute"}

    def __init__(self, scope: str | None = None):
        super().__init__()
        if scope:
            self.scope = scope
            self.rate = self.scope_rates.get(scope)


class ThrottleMiddleware(Middleware):
    """Middleware that applies multiple throttle classes."""

    def __init__(self, throttle_classes: list[type[BaseThrottle]] | None = None):
        self.throttles = [cls() for cls in (throttle_classes or [AnonRateThrottle])]

    async def process(self, request_data, call_next):
        for throttle in self.throttles:
            if not throttle.allow_request(request_data):
                wait = throttle.wait()
                resp = json_error_response(429, "Too Many Requests")
                if wait is not None:
                    resp["headers"].append(("retry-after", str(int(wait) + 1)))
                return resp
        return await call_next(request_data)
