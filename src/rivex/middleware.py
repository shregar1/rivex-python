from __future__ import annotations

from collections.abc import Callable

from rivex._compat import (
    RC_V2,
    apply_compressed_headers,
    client_ip,
    get_request_header,
    json_error_response,
)
from rivex._compat import (
    rc as _rc,
)


class Middleware:
    async def process(self, request_data: dict, call_next: Callable) -> dict:
        result: dict = await call_next(request_data)
        return result


_CORS_SAFE_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD")


class CORSMiddleware(Middleware):
    def __init__(
        self,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        allow_credentials: bool = False,
        max_age: int = 600,
    ):
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
        self.max_age = max_age

        # CORS spec forbids ``*`` in Access-Control-Allow-Methods /
        # Access-Control-Allow-Headers when credentials are sent —
        # browsers reject the preflight (Chrome silently, curl works fine).
        # Warn the operator AND auto-expand ``*`` per-request so existing
        # apps don't break in browsers while the config is being fixed.
        if self.allow_credentials and (
            "*" in self.allow_methods or "*" in self.allow_headers
        ):
            import warnings

            offenders = []
            if "*" in self.allow_methods:
                offenders.append("allow_methods")
            if "*" in self.allow_headers:
                offenders.append("allow_headers")
            warnings.warn(
                "CORSMiddleware: allow_credentials=True is incompatible with "
                f"wildcard {' / '.join(offenders)} per the CORS spec — "
                "browsers reject the preflight response.  Rivex will expand "
                "'*' from the request at runtime, but you should enumerate "
                "the methods/headers your API needs (e.g. "
                "allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'], "
                "allow_headers=['content-type','authorization']).",
                stacklevel=2,
            )

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        origin = get_request_header(request_data, "origin")
        if request_data.get("method") == "OPTIONS":
            requested_method = get_request_header(
                request_data, "access-control-request-method"
            )
            requested_headers = get_request_header(
                request_data, "access-control-request-headers"
            )
            return {
                "status": 204,
                "headers": self._cors_headers(
                    origin,
                    requested_method=requested_method,
                    requested_headers=requested_headers,
                ),
                "body": b"",
            }

        response: dict = await call_next(request_data)
        response["headers"] = response.get("headers", []) + self._cors_headers(origin)
        return response

    def _cors_headers(
        self,
        request_origin: str | None = None,
        *,
        requested_method: str | None = None,
        requested_headers: str | None = None,
    ) -> list[tuple[str, str]]:
        # Expand wildcards when credentials are on — the Rust core respects
        # the same lists we pass in, so we expand *here* and hand it the
        # concrete values.  When credentials are off, ``*`` is legal.
        allow_methods = self.allow_methods
        allow_headers = self.allow_headers
        if self.allow_credentials:
            if "*" in allow_methods:
                if requested_method:
                    allow_methods = [requested_method]
                else:
                    allow_methods = list(_CORS_SAFE_METHODS)
            if "*" in allow_headers:
                if requested_headers:
                    # Echo back what the browser asked for, normalised.
                    allow_headers = [
                        h.strip() for h in requested_headers.split(",") if h.strip()
                    ]
                else:
                    # No preflight context → punt to a permissive default.
                    allow_headers = ["content-type", "authorization", "accept"]

        if RC_V2:
            return list(
                _rc.build_cors_headers(
                    request_origin or "",
                    self.allow_origins,
                    allow_methods,
                    allow_headers,
                    [],
                    self.allow_credentials,
                    self.max_age,
                    True,
                )
            )
        if "*" in self.allow_origins:
            if self.allow_credentials:
                allowed_origin = request_origin or "*"
            else:
                allowed_origin = "*"
        elif request_origin and request_origin in self.allow_origins:
            allowed_origin = request_origin
        elif request_origin:
            allowed_origin = self.allow_origins[0] if self.allow_origins else ""
        else:
            allowed_origin = self.allow_origins[0] if self.allow_origins else ""

        headers: list[tuple[str, str]] = [
            ("access-control-allow-origin", allowed_origin),
            ("access-control-allow-methods", ", ".join(allow_methods)),
            ("access-control-allow-headers", ", ".join(allow_headers)),
            ("access-control-max-age", str(self.max_age)),
        ]
        if self.allow_credentials:
            headers.append(("access-control-allow-credentials", "true"))
        if "*" not in self.allow_origins:
            headers.append(("vary", "Origin"))
        return headers


class RequestIdMiddleware(Middleware):
    def __init__(self, header_name: str = "x-request-id"):
        self.header_name = header_name

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        incoming_id = get_request_header(request_data, self.header_name)

        if incoming_id:
            request_id = incoming_id
        elif RC_V2:
            request_id = _rc.generate_request_id()
        else:
            import uuid

            request_id = uuid.uuid4().hex
        response: dict = await call_next(request_data)
        response["headers"] = response.get("headers", []) + [(self.header_name, request_id)]
        return response


class GZipMiddleware(Middleware):
    def __init__(self, minimum_size: int = 500):
        self.minimum_size = minimum_size

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        response: dict = await call_next(request_data)
        body = response.get("body", b"")
        if len(body) < self.minimum_size:
            return response

        accept = get_request_header(request_data, "accept-encoding") or ""
        if "gzip" not in accept.lower():
            return response

        if RC_V2:
            compressed = _rc.gzip_compress(body)
        else:
            import gzip

            compressed = gzip.compress(body)
        if len(compressed) >= len(body):
            return response

        response["body"] = compressed
        apply_compressed_headers(response, "gzip")
        return response


class TrustedHostMiddleware(Middleware):
    def __init__(self, allowed_hosts: list[str] | None = None):
        self.allowed_hosts = set(h.lower() for h in (allowed_hosts or ["*"]))

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        if "*" in self.allowed_hosts:
            result: dict = await call_next(request_data)
            return result

        host_header = get_request_header(request_data, "host") or ""

        if RC_V2:
            trusted = _rc.check_trusted_host(host_header, list(self.allowed_hosts))
        else:
            host = host_header.split(":")[0].lower()
            trusted = host in self.allowed_hosts

        if not trusted:
            return json_error_response(400, "Invalid host header")
        result = await call_next(request_data)
        return result


class HTTPSRedirectMiddleware(Middleware):
    async def process(self, request_data: dict, call_next: Callable) -> dict:
        scheme = get_request_header(request_data, "x-forwarded-proto") or "http"
        host = get_request_header(request_data, "host") or ""

        if scheme.strip() != "https":
            path = request_data.get("path", "/")
            qs = request_data.get("query_string", "")
            if RC_V2:
                url = _rc.build_redirect_url(path, qs, host)
            else:
                url = f"https://{host}{path}"
                if qs:
                    url = f"{url}?{qs}"
            return {
                "status": 307,
                "headers": [("location", url)],
                "body": b"",
            }

        result: dict = await call_next(request_data)
        return result


class MaxBodySizeMiddleware(Middleware):
    def __init__(self, max_size: int = 1_048_576):  # 1MB default
        self.max_size = max_size

    async def process(self, request_data: dict, call_next):
        body = request_data.get("body", b"")
        if isinstance(body, bytes) and len(body) > self.max_size:
            return json_error_response(413, "Request body too large")
        return await call_next(request_data)


class RateLimitMiddleware(Middleware):
    """Token-bucket rate limiter with per-IP, per-user, and global buckets.

    The *strategy* controls which key is used to identify the client:
    ``"ip"`` (default), ``"user"`` (JWT sub claim), or ``"global"``.

    Multiple instances can be stacked for different limit tiers::

        # IP-based: 100 req/min
        app.add_middleware(RateLimitMiddleware, rate=100, per=60)

        # User-based: 1000 req/min
        app.add_middleware(RateLimitMiddleware, rate=1000, per=60, strategy="user")
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
        self._buckets: dict[str, list] = {}

    def _key(self, request_data: dict) -> str:
        if self.strategy == "user":
            for k, v in request_data.get("headers", []):
                if k.lower() == "authorization":
                    return v
            return "anonymous"
        if self.strategy == "global":
            return "_global"
        if self.key_header:
            val = get_request_header(request_data, self.key_header)
            if val:
                return val
        return client_ip(request_data)

    async def process(self, request_data: dict, call_next):
        import time

        key = self._key(request_data)
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, [0.0, self.rate])
        last, tokens = bucket
        elapsed = now - last
        tokens = min(self.rate, tokens + elapsed * (self.rate / self.per))
        if tokens < 1:
            resp = json_error_response(429, "Too Many Requests")
            resp["headers"].append(("retry-after", str(int(self.per / self.rate))))
            return resp
        bucket[0] = now
        bucket[1] = tokens - 1
        return await call_next(request_data)


class AccessLogMiddleware(Middleware):
    """Logs each request in Apache combined-like format."""

    def __init__(self, logger_name: str = "rivex.access"):
        import logging

        self.logger = logging.getLogger(logger_name)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    async def process(self, request_data: dict, call_next):
        import time

        start = time.monotonic()
        response: dict = await call_next(request_data)
        elapsed = (time.monotonic() - start) * 1000
        method = request_data.get("method", "?")
        path = request_data.get("path", "/")
        status = response.get("status", 0) if isinstance(response, dict) else 0
        ip = client_ip(request_data)
        self.logger.info(f'{ip} "{method} {path}" {status} {elapsed:.1f}ms')
        return response


class SecurityHeadersMiddleware(Middleware):
    """Adds common security headers to responses."""

    def __init__(
        self,
        hsts: bool = True,
        hsts_max_age: int = 31536000,
        hsts_include_subdomains: bool = True,
        content_type_nosniff: bool = True,
        frame_options: str | None = "DENY",
        xss_protection: bool = True,
        referrer_policy: str = "strict-origin-when-cross-origin",
    ):
        self._headers: list[tuple[str, str]] = []
        if hsts:
            val = f"max-age={hsts_max_age}"
            if hsts_include_subdomains:
                val += "; includeSubDomains"
            self._headers.append(("strict-transport-security", val))
        if content_type_nosniff:
            self._headers.append(("x-content-type-options", "nosniff"))
        if frame_options:
            self._headers.append(("x-frame-options", frame_options))
        if xss_protection:
            self._headers.append(("x-xss-protection", "1; mode=block"))
        if referrer_policy:
            self._headers.append(("referrer-policy", referrer_policy))

    async def process(self, request_data: dict, call_next):
        response: dict = await call_next(request_data)
        if isinstance(response, dict):
            headers = list(response.get("headers", []))
            headers.extend(self._headers)
            response["headers"] = headers
        return response


class TrailingSlashMiddleware(Middleware):
    """Redirects or strips trailing slashes for consistent URLs."""

    def __init__(self, redirect: bool = True, action: str = "strip"):
        self.redirect = redirect
        self.action = action  # "strip" or "append"

    async def process(self, request_data: dict, call_next):
        path = request_data.get("path", "/")
        if path != "/" and len(path) > 1:
            if self.action == "strip" and path.endswith("/"):
                new_path = path.rstrip("/")
            elif self.action == "append" and not path.endswith("/"):
                new_path = path + "/"
            else:
                new_path = None

            if new_path and new_path != path:
                if self.redirect:
                    qs = request_data.get("query_string", "")
                    location = new_path + ("?" + qs if qs else "")
                    return {
                        "status": 307,
                        "headers": [("location", location)],
                        "body": b"",
                    }
                request_data = dict(request_data)
                request_data["path"] = new_path

        return await call_next(request_data)


class TimeoutMiddleware(Middleware):
    """Kills slow handlers after a timeout period."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        import asyncio

        try:
            result: dict = await asyncio.wait_for(call_next(request_data), timeout=self.timeout)
            return result
        except asyncio.TimeoutError:
            return json_error_response(504, "Request Timeout")


class IPFilterMiddleware(Middleware):
    """Allow/deny requests by client IP address. Supports CIDR notation."""

    def __init__(
        self,
        allow: list[str] | None = None,
        deny: list[str] | None = None,
    ):
        import ipaddress

        self._allow = [ipaddress.ip_network(a, strict=False) for a in allow] if allow else []
        self._deny = [ipaddress.ip_network(d, strict=False) for d in deny] if deny else []

    def _is_blocked(self, ip_str: str) -> bool:
        import ipaddress

        addr = ipaddress.ip_address(ip_str)
        if self._deny:
            for net in self._deny:
                if addr in net:
                    return True
        if self._allow:
            for net in self._allow:
                if addr in net:
                    return False
            return True
        return False

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        ip = client_ip(request_data)
        if self._is_blocked(ip):
            return json_error_response(403, "Forbidden")
        result: dict = await call_next(request_data)
        return result


class CompressionMiddleware(Middleware):
    """Response compression with brotli and gzip support."""

    def __init__(self, minimum_size: int = 500, level: int = 4):
        self.minimum_size = minimum_size
        self.level = level

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        response: dict = await call_next(request_data)
        body = response.get("body", b"")
        if len(body) < self.minimum_size:
            return response

        for k, _v in response.get("headers", []):
            if k.lower() == "content-encoding":
                return response

        accept = (get_request_header(request_data, "accept-encoding") or "").lower()

        compressed = None
        encoding = None

        if "br" in accept:
            try:
                import brotli

                compressed = brotli.compress(body, quality=self.level)
                encoding = "br"
            except ImportError:
                pass

        if compressed is None and "gzip" in accept:
            if RC_V2:
                compressed = _rc.gzip_compress(body)
            else:
                import gzip

                compressed = gzip.compress(body, compresslevel=self.level)
            encoding = "gzip"

        if compressed is None and "deflate" in accept:
            import zlib

            compressed = zlib.compress(body, self.level)
            encoding = "deflate"

        if compressed is None or len(compressed) >= len(body):
            return response

        response["body"] = compressed
        assert encoding is not None
        apply_compressed_headers(response, encoding)
        return response


class IdempotencyMiddleware(Middleware):
    """Stripe-style idempotency key support for safe retries."""

    def __init__(
        self,
        header_name: str = "idempotency-key",
        ttl: float = 86400.0,
        max_entries: int = 10000,
    ):
        self.header_name = header_name
        self.ttl = ttl
        self.max_entries = max_entries
        self._cache: dict[str, tuple[float, dict]] = {}

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        import time

        method = request_data.get("method", "").upper()
        if method not in ("POST", "PUT", "PATCH"):
            result: dict = await call_next(request_data)
            return result

        key = get_request_header(request_data, self.header_name)
        if key is None:
            result = await call_next(request_data)
            return result

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


class MethodOverrideMiddleware(Middleware):
    def __init__(self, header_name: str = "X-HTTP-Method-Override"):
        self._header = header_name.lower()

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        override = get_request_header(request_data, self._header)
        if override:
            request_data = dict(request_data)
            request_data["method"] = override.upper()
        result: dict = await call_next(request_data)
        return result
