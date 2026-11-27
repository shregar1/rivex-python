# API Reference

A condensed map of what you import and where it's documented. Everything below is available from the top-level `rivex` package unless a submodule is noted.

## Core

```python
from rivex import Rivex, FastAPI          # the application (FastAPI is an alias)
from rivex import Router, APIRouter        # route groups
from rivex import Controller, RouteGroup   # class-based & scoped routes
from rivex import route, get, post, put, delete, patch, head, options
from rivex import Request                  # the request object
from rivex import TestClient               # in-process test client
```

`Rivex(title, version, description, debug, docs_url, redoc_url, openapi_url, ...)` ·
`app.run(host, port, workers)` · `app.add_middleware(cls, **kw)` ·
`app.include_router(r)` · `app.include_controller(c)` ·
`app.on_event("startup"|"shutdown")` · `app.exception_handler(Exc)` ·
`app.middleware("http")` · `app.websocket(path)` · `app.mount(path, app)` ·
`app.url_for(name, **params)` → *Routing*

## Parameters & validation

```python
from rivex import Path, Query, Header, Cookie, Body
from rivex import Schema, Field            # native validation models
from rivex import UploadFile, File, Form   # multipart uploads & form fields
from rivex import jsonable_encoder
from rivex import serialize, deserialize, set_serializer
```
→ *Parameters & Validation*, *Requests & Responses*

## Responses

```python
from rivex import (
    Response, JSONResponse, HTMLResponse, PlainTextResponse,
    RedirectResponse, StreamingResponse, EventSourceResponse,
    FileResponse, XMLResponse,
)
from rivex import status                   # HTTP status constants
from rivex import HTTPException, RequestValidationError
```
→ *Requests & Responses*

## Dependency injection

```python
from rivex import Depends, Dependency
```
`Depends(callable, use_cache=True, scope="request"|"singleton")` → *Dependency Injection*

## Middleware

```python
from rivex import (
    Middleware, CORSMiddleware, GZipMiddleware, CompressionMiddleware,
    SecurityHeadersMiddleware, TrustedHostMiddleware, HTTPSRedirectMiddleware,
    RateLimitMiddleware, TimeoutMiddleware, IPFilterMiddleware,
    MaxBodySizeMiddleware, MethodOverrideMiddleware, TrailingSlashMiddleware,
    IdempotencyMiddleware, RequestIdMiddleware, AccessLogMiddleware,
    CSRFMiddleware, SessionMiddleware,
)
```
→ *Middleware*

## Security & auth

```python
from rivex import (
    APIKeyHeader, APIKeyQuery, APIKeyCookie,
    HTTPBearer, HTTPBasic, HTTPAuthorizationCredentials, HTTPBasicCredentials,
    OAuth2PasswordBearer, OAuth2AuthorizationCodeBearer,
    OAuth2PasswordRequestForm, SecurityScopes,
    Guard, GuardMiddleware, IsAuthenticated, RequiresRoles, AllowAll, DenyAll,
    hash_password, verify_password, hash_bcrypt, hash_argon2,
    validate_email, validate_url, validate_ip, validate_uuid, validate_phone,
    validate_iban, format_iban, luhn_check, is_ascii,
    sanitize_html, strip_html_tags,
)
from rivex.jwt import encode, decode, JWTBearer, ExpiredTokenError, InvalidTokenError
from rivex.webhooks import verify_signature, WebhookGuard, WebhookVerificationError
```
→ *Security & Authentication*

## Throttling

```python
from rivex import (
    BaseThrottle, AnonRateThrottle, UserRateThrottle,
    ScopedRateThrottle, ThrottleMiddleware,
)
```
→ *Security & Authentication*

## Real-time & async

```python
from rivex import WebSocket, WebSocketDisconnect
from rivex.ws import ConnectionManager
from rivex import BackgroundTask, BackgroundTasks
from rivex import run_in_threadpool
```
→ *WebSockets*, *Background Tasks & Concurrency*

## Performance

```python
from rivex.gen import gen, F, JsonBytes
from rivex.negotiation import parse_accept, best_match
from rivex.pagination import Page, CursorPage, paginate
from rivex.caching import CacheMiddleware, ETagMiddleware, cached_response
```
→ *High-Performance JSON*, *Middleware*

## Errors (RFC 7807)

```python
from rivex.problem import (
    ProblemDetail, ProblemException, ProblemResponse, problem_exception_handler,
    not_found, bad_request, unauthorized, forbidden, conflict,
    unprocessable, internal_error,
)
```
→ *Requests & Responses*, *Observability*

## Observability

```python
from rivex.metrics import Counter, Gauge, Histogram, MetricsRegistry, MetricsMiddleware
from rivex.tracing import (
    Span, SpanExporter, ConsoleSpanExporter, OTelSpanExporter,
    TracingMiddleware, configure_tracing,
)
from rivex.structlog import (
    JSONFormatter, StructuredLogger, StructuredAccessLogMiddleware, configure_logging,
)
from rivex.health import HealthCheck
from rivex.events import (
    Signal, request_started, request_finished, request_failed,
    server_startup, server_shutdown,
)
from rivex_monitor import (
    MonitorMiddleware, MonitoredConnectionManager,
    register_monitor_partials,
    observe_http, observe_ws, observe_webrtc, observe_grpc,
    get_http_snapshot, get_ws_snapshot, get_webrtc_snapshot,
    get_grpc_snapshot, get_adapter_snapshot, get_health_snapshot,
)
```
→ *Observability*

## Configuration, templates & versioning

```python
from rivex import Settings
from rivex.templating import Jinja2Templates
from rivex.staticfiles import StaticFiles
from rivex import (
    BaseVersioning, URLPathVersioning, HeaderVersioning,
    QueryParamVersioning, AcceptHeaderVersioning, VersionMiddleware,
)
```
→ *Configuration & Deployment*

## Command line

```bash
rivex run main:app [--host H] [--port P] [--workers N] [--reload]
rivex routes main:app
rivex version
```
→ *Configuration & Deployment*

---

*Documentation for Rivex 0.1.0 — built and published with DOCX, part of the vexarr ecosystem.*
