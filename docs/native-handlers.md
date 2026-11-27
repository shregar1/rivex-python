# Native Handlers — Rust-Speed Responses for Common Patterns

Native handlers pre-compute responses at **startup** and register them as
Rust-side **const routes**. At request time, the Rust core serves them from
an O(1) `HashMap` lookup — Python is never invoked.

## Quick Start

```python
from rivex import Rivex
from rivex.native import NativeHandlers

app = Rivex()

# Static files — walks directory at startup, registers each file as a const route
NativeHandlers.serve_static(app, "/static", "./public",
                            cache_control="public, max-age=31536000",
                            exclude=["*.tmp", "*.log"])

# Health check — sub-microsecond response for Kubernetes probes
NativeHandlers.health(app, "/health", body={"status": "ok"})

# OpenAPI spec — pre-baked JSON, served at Rust speed
NativeHandlers.openapi(app, "/openapi.json", spec=my_spec)

# Redirects — 301/302 as const routes
NativeHandlers.redirect(app, "/old-page", "/new-page", permanent=True)

app.run()
```

## How It Works

```
┌─────────────────────────────────────────────────────┐
│ STARTUP (Python)                                    │
│                                                     │
│  serve_static() walks directory                     │
│  health() serialises body to JSON                   │
│  openapi() generates spec                           │
│  redirect() builds 301 response                     │
│         │                                           │
│         ▼                                           │
│  app.add_const_route(method, path, status, body, headers)
│         │                                           │
│         ▼                                           │
│  Rust HashMap<(method, path), Response>             │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ REQUEST TIME (Rust only — no Python)                │
│                                                     │
│  HTTP request ──► matchit trie                      │
│                ──► const route cache HIT            │
│                ──► write pre-baked bytes to socket  │
│                ──► done                             │
│                                                     │
│  ~1-2 µs per response                               │
│  ~500K+ requests/sec (4 workers)                    │
└─────────────────────────────────────────────────────┘
```

## Patterns

### 1. Static File Serving

Serves an entire directory of static files (CSS, JS, images, fonts) as
Rust const routes. Each file is read once at startup and cached in the
Rust HashMap.

```python
NativeHandlers.serve_static(
    app,
    route="/assets",           # URL prefix
    directory="./public",      # filesystem path
    index_file="index.html",   # serve this for directory URLs
    cache_control="public, max-age=31536000",  # 1 year cache
    exclude=["*.tmp", "*.log", ".*"],  # skip these
    max_file_size=10 * 1024 * 1024,     # skip files > 10 MB
)
```

**Path traversal protection**: Uses `rivex_core.resolve_static_path()` which
canonicalises both the root directory and the requested path, then verifies
the resolved path is inside the root (CWE-22 guard — same pattern as
`actix-files` and `tower-http::ServeDir`).

**Limitations**: Files are loaded into memory. For directories larger than
~500 MB, use a streaming file server instead. Files are read once at
startup; disk changes require an app restart.

### 2. Health / Liveness Check

```python
# Default: 200 {"status": "ok"}
NativeHandlers.health(app, "/health")

# Custom body and status
NativeHandlers.health(app, "/healthz",
    status=200,
    body={"status": "healthy", "version": "1.2.3"},
    content_type="application/json",
    cache_control="no-cache",
)

# Plaintext health check
NativeHandlers.health(app, "/live",
    body="OK",
    content_type="text/plain",
)
```

For **readiness checks** that depend on external state (DB, cache), use a
regular Python handler — native health is for "is this process alive?" only.

### 3. OpenAPI Spec

```python
# Auto-generate from registered routes
NativeHandlers.openapi(app, "/openapi.json")

# Explicit spec
NativeHandlers.openapi(app, "/api.json", spec={
    "openapi": "3.0.0",
    "info": {"title": "My API", "version": "1.0"},
    "paths": {...}
})
```

### 4. Redirects

```python
# Permanent (301) — cached by browsers indefinitely
NativeHandlers.redirect(app, "/old", "/new", permanent=True)

# Temporary (302) — for A/B tests, maintenance pages
NativeHandlers.redirect(app, "/app", "/maintenance", permanent=False)

# External URL
NativeHandlers.redirect(app, "/docs", "https://docs.example.com")
```

## Importing Individual Functions

```python
from rivex.native import serve_static, health, openapi, redirect
from rivex.native import raw_response, raw_json, raw_text, raw_html

serve_static(app, "/static", "./public")
health(app, "/health")
openapi(app, "/openapi.json")
redirect(app, "/old", "/new")
```

## Raw Response Helpers — Skip Normalization for Dynamic Handlers

For dynamic handlers (database queries, computed responses), you can
skip the framework's response normalization layer entirely. Serialise
the body yourself and return a pre-built response dict:

```python
from rivex_core import json_serialize
from rivex.native.raw import raw_json

@app.get("/users/{id}")
def get_user(id: int):
    user = db.fetch_one(id)
    # Serialise via Rust, build response directly — skips _normalize_response_fast
    return raw_json(json_serialize(user))
```

**Performance**: ~11% faster than returning a plain dict (98K vs 88K RPS
on in-memory benchmarks). The framework detects the `_rivex_raw` marker
and passes the dict straight to Rust without inspecting or re-serialising it.

Available helpers:
- `raw_json(body: bytes)` — `Content-Type: application/json`
- `raw_text(body: bytes | str)` — `Content-Type: text/plain; charset=utf-8`
- `raw_html(body: bytes | str)` — `Content-Type: text/html; charset=utf-8`
- `raw_response(body, content_type=..., status=..., headers=...)` — full control

## Coexistence with Python Routes

Native handlers and regular Python routes coexist without conflict:

```python
@app.get("/api/users")
def get_users():
    return {"users": [...]}  # Python handler

NativeHandlers.health(app, "/health")  # Rust const route
NativeHandlers.serve_static(app, "/static", "./public")  # Rust const routes
```

The Rust core checks the const route cache **before** the matchit trie.
If a request matches a const route, Python is never invoked. Otherwise,
the normal Python handler runs.

## Performance

Benchmarked on Azure D32s_v5 (32 vCPU), 4 workers, `wrk -t4 -c64 -d10s`:

| Endpoint | Python handler | Native handler | Speedup |
|---|---|---|---|
| `/health` | ~90K RPS | ~555K RPS | **6.2×** |
| `/openapi.json` | ~85K RPS | ~555K RPS | **6.5×** |
| `/static/style.css` | ~80K RPS | ~550K RPS | **6.9×** |
| `/redirect` | ~85K RPS | ~555K RPS | **6.5×** |

Native handlers match `const=True` throughput because they use the same
Rust HashMap lookup mechanism.

## When to Use Native Handlers vs Python Handlers

| Use native when... | Use Python when... |
|---|---|
| Response is constant (never changes between deploys) | Response depends on request data (params, body, auth) |
| Endpoint is a health/readiness probe | Endpoint queries a database |
| Serving static assets (CSS, JS, images) | Endpoint runs business logic |
| Serving OpenAPI/JSON schema specs | Endpoint streams responses (SSE, NDJSON) |
| HTTP redirects that don't change | Response requires middleware (auth, CORS) |

## Security Notes

- **Path traversal**: `serve_static()` uses `resolve_static_path()` from the
  Rust core, which canonicalises paths and verifies they're inside the root
  directory. This prevents `../../../etc/passwd` attacks (CWE-22).
- **Memory limits**: `max_file_size` (default 10 MB) prevents accidentally
  loading large files into memory. Set it lower for strict environments.
- **Exclusion patterns**: Use `exclude=["*.env", "*.key", ".*"]` to prevent
  serving sensitive files.
- **Cache headers**: Health checks default to `Cache-Control: no-cache` so
  probes don't get cached by intermediaries.
