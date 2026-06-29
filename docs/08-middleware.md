# Middleware

Middleware wraps every request and response — for logging, compression, security headers, rate limiting, and more. Rivex ships a large catalogue of production-ready middleware and lets you write your own as a function or a class.

## Adding middleware

Attach middleware with `add_middleware(Class, **options)`:

```python
from rivex import CORSMiddleware, GZipMiddleware, Rivex

app = Rivex()
app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"], allow_credentials=True)
app.add_middleware(GZipMiddleware, minimum_size=500)
```

**Ordering.** Middleware runs last-added-first (LIFO) on the way in. Add cross-cutting concerns like request IDs and logging early so they wrap everything else.

## Writing your own

### Function middleware

```python
from rivex import Request


@app.middleware("http")
async def add_timing(request: Request, call_next):
    response = await call_next(request)
    response["headers"] = response.get("headers", []) + [("x-powered-by", "rivex")]
    return response
```

### Class middleware

```python
from rivex import Middleware


class RequestSourceMiddleware(Middleware):
    async def process(self, request_data: dict, call_next):
        response = await call_next(request_data)
        response["headers"] = response.get("headers", []) + [("x-request-source", "api")]
        return response


app.add_middleware(RequestSourceMiddleware)
```

Both forms call `call_next(...)` to continue the chain and return the (possibly modified) response.

## Built-in middleware

All are importable from `rivex`. Defaults shown are the common ones — see each class for the full set.

### CORS & transport

| Middleware | Key options | Purpose |
| --- | --- | --- |
| `CORSMiddleware` | `allow_origins`, `allow_methods`, `allow_headers`, `allow_credentials`, `max_age=600` | Cross-origin requests + preflight |
| `GZipMiddleware` | `minimum_size=500` | gzip compression |
| `CompressionMiddleware` | `minimum_size=500`, `level=4` | brotli → gzip → deflate, by `Accept-Encoding` |
| `HTTPSRedirectMiddleware` | — | Redirect HTTP → HTTPS (honours `X-Forwarded-Proto`) |
| `TrailingSlashMiddleware` | `redirect=True`, `action="strip"` | Canonicalize trailing slashes |
| `MethodOverrideMiddleware` | `header_name="X-HTTP-Method-Override"` | Override method via header |

### Security & access control

| Middleware | Key options | Purpose |
| --- | --- | --- |
| `SecurityHeadersMiddleware` | `hsts=True`, `frame_options="DENY"`, `referrer_policy=...` | HSTS, `X-Frame-Options`, nosniff, etc. |
| `TrustedHostMiddleware` | `allowed_hosts=["*"]` | Reject unexpected `Host` headers (`400`) |
| `IPFilterMiddleware` | `allow=[...CIDR]`, `deny=[...CIDR]` | Allow/deny by client IP |
| `MaxBodySizeMiddleware` | `max_size=1_048_576` | Reject oversized bodies (`413`) |
| `RateLimitMiddleware` | `rate=100`, `per=60.0` | Token-bucket rate limit per IP (`429`) |
| `TimeoutMiddleware` | `timeout=30.0` | Abort slow handlers (`504`) |
| `CSRFMiddleware` | `secret_key`, `exempt_paths=[...]` | Double-submit cookie CSRF protection |
| `SessionMiddleware` | `secret_key`, `max_age`, `https_only` | Signed-cookie sessions on `request.session` |

### Operations

| Middleware | Key options | Purpose |
| --- | --- | --- |
| `RequestIdMiddleware` | `header_name="x-request-id"` | Generate/propagate a request id |
| `AccessLogMiddleware` | `logger_name="rivex.access"` | Combined-format access logs |
| `IdempotencyMiddleware` | `header_name="idempotency-key"`, `ttl=86400` | Cache responses for replayed write keys |

## Examples

Harden a public API:

```python
from rivex import (
    Rivex, CORSMiddleware, SecurityHeadersMiddleware,
    RateLimitMiddleware, RequestIdMiddleware, CompressionMiddleware,
)

app = Rivex()
app.add_middleware(RequestIdMiddleware)               # outermost: tags everything
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, rate=1000, per=3600.0)
app.add_middleware(CompressionMiddleware, minimum_size=500)
app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"])
```

Cookie sessions:

```python
from rivex import Request, SessionMiddleware

app.add_middleware(SessionMiddleware, secret_key="change-me", https_only=True)


@app.get("/visit")
async def visit(request: Request):
    request.session["count"] = request.session.get("count", 0) + 1
    return {"count": request.session["count"]}
```

## Related

For request throttling by user vs. anonymous, and for permission guards, see **Security & Authentication**, which covers `ThrottleMiddleware`, `GuardMiddleware`, and the security schemes.
