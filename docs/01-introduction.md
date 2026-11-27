# Introduction

Rivex is a **Rust-powered Python web framework with FastAPI-like ergonomics**. You write ordinary, type-annotated Python handlers; a native Rust HTTP core (`rivex-core`) accepts connections, parses requests, and drives your code on worker threads. The result is a familiar developer experience with a much faster floor.

> **Version.** This documentation tracks Rivex **0.1.0**. The public API is imported straight from the top-level `rivex` package — e.g. `from rivex import Rivex`.

## Why Rivex

- **Familiar, FastAPI-style API.** Decorator routes (`@app.get(...)`), dependency injection with `Depends()`, Pydantic request/response models, and auto-generated OpenAPI docs. If you know FastAPI, you already know most of Rivex. The application class is even exported as `FastAPI` for drop-in muscle memory.
- **A Rust core, not just an ASGI shim.** The server, request parsing, JSON encoding, password hashing, JWT, and a suite of validators are implemented in Rust and exposed to Python. You opt into the fast paths without leaving Python.
- **Batteries included.** Twenty-plus production middleware (CORS, compression, rate limiting, security headers, sessions, CSRF, idempotency…), security schemes, JWT, guards, throttling, websockets, background tasks, caching, pagination, metrics, tracing, structured logging, health checks, and settings — all in the box.
- **Two validation engines.** Use Pydantic `BaseModel` if you like, or  own lighter-weight `Schema`. They are interchangeable at the handler boundary.
- **Native JSON generation.** The `gen` API builds large JSON payloads entirely in Rust — no intermediate Python objects — for throughput that ordinary list comprehensions can't reach.

## How a request flows

```
   Client
     │  HTTP
     ▼
┌─────────────────────────────┐
│  rivex-core  (Rust)         │   accept, parse, route match,
│  async runtime + workers    │   JSON encode, TLS, keep-alive
└──────────────┬──────────────┘
               │  calls your handler on a worker thread
               ▼
┌─────────────────────────────┐
│  Your Python handlers        │   dependency injection, validation,
│  middleware · DI · models    │   business logic, response objects
└─────────────────────────────┘
```

Handlers may be `async def` or plain `def` — Rivex runs both correctly. Because handlers execute on Rust worker threads, blocking/CPU-bound work should be offloaded with [`run_in_threadpool`](#) (see *Background Tasks & Concurrency*).

## A taste

```python
from rivex import Rivex

app = Rivex(title="Hello API", version="1.0.0")


@app.get("/")
async def index():
    return {"message": "Hello from Rivex"}


@app.get("/users/{user_id}")
async def get_user(user_id: int, verbose: bool = False):
    return {"id": user_id, "verbose": verbose}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
```

Return a `dict` or a Pydantic/Schema model and Rivex serializes it to JSON automatically. Visit `http://localhost:8000/docs` for interactive Swagger UI generated from your route signatures.

## What's in these docs

| Section | You'll learn |
| --- | --- |
| **Installation** | Install Rivex and its optional extras |
| **Quickstart** | Build and run a small API in a few minutes |
| **Routing** | Function routes, controllers, routers, path/query params |
| **Parameters & Validation** | `Path`/`Query`/`Header`/`Cookie`/`Body`, Pydantic & `Schema` |
| **Requests & Responses** | The `Request` object and every response type |
| **Dependency Injection** | `Depends()`, class dependencies, caching, scopes |
| **Middleware** | The full built-in middleware catalogue |
| **Security & Authentication** | API keys, Bearer/Basic, OAuth2, JWT, password hashing, guards |
| **WebSockets** | Real-time handlers and broadcast rooms |
| **Background Tasks & Concurrency** | Deferred work and offloading blocking code |
| **High-Performance JSON** | The Rust-native `gen` generator |
| **OpenAPI & Docs** | Customizing the auto-generated schema and UIs |
| **Testing** | The in-process `TestClient` |
| **Observability** | Metrics, tracing, structured logs, health checks |
| **Configuration & Deployment** | `Settings`, the CLI, workers, Docker |
| **API Reference** | A one-page import cheat sheet |

Rivex is released under the **MIT license** and requires **Python 3.10+**.
