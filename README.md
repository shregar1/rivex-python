# Rivex Python SDK

**A Rust-powered Python web framework with FastAPI-like ergonomics.** You write
ordinary, type-annotated Python handlers; a native Rust HTTP core
(`rivex-core`) accepts connections, parses requests, encodes JSON, and drives
your code on worker threads. Familiar developer experience, much faster floor.

```python
from rivex import Rivex

app = Rivex(title="Hello API", version="1.0.0")


@app.get("/users/{user_id}")
async def get_user(user_id: int, verbose: bool = False):
    return {"id": user_id, "verbose": verbose}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)   # interactive docs at /docs
```

---

## Why Rivex

- **Familiar, FastAPI-style API** — decorator routes, `Depends()` dependency
  injection, Pydantic models, auto-generated OpenAPI. The app class is even
  exported as `FastAPI` for drop-in muscle memory.
- **A Rust core, not just an ASGI shim** — the server, request parsing, JSON
  encoding, password hashing, JWT, and a suite of validators run in Rust and
  are exposed to Python. You opt into the fast paths without leaving Python.
- **Batteries included** — 20+ production middleware, security schemes, JWT,
  guards, throttling, websockets, background tasks, caching, pagination,
  metrics, tracing, structured logging, health checks, settings, and a
  real-time monitoring dashboard (`rivex_monitor`) with per-protocol
  HTTP/WS/WebRTC/gRPC metrics.
- **Two validation engines** — use Pydantic `BaseModel`, or Rivex's lighter
  `Schema`. They're interchangeable at the handler boundary.
- **Native JSON generation** — the `gen` API builds large JSON payloads
  entirely in Rust, with no intermediate Python objects.

## Requirements

- **Python 3.10+**
- The compiled Rust core is **bundled inside the `rivex` wheel** — there is no
  separate `rivex-core` package to install. `pip install rivex` fetches one
  self-contained prebuilt wheel for your platform.
- Pure-Python dependencies (installed automatically): `pydantic>=2.0`, `orjson>=3.9`.

## Installation

```bash
pip install rivex
```

Optional extras:

```bash
pip install "rivex[schemax]"   # Schemax IDL toolchain (rivex schemax …)
pip install "rivex[dev]"       # pytest, httpx, mypy, ruff for development
```

Verify the install:

```bash
rivex version        # → Rivex 0.1.0
```

## Quickstart

Build a small CRUD API (the full version lives in [`examples/todo_api.py`](examples/todo_api.py)):

```python
from pydantic import BaseModel

from rivex import CORSMiddleware, HTTPException, Rivex, Router

app = Rivex(title="Todo API", debug=True)
app.add_middleware(CORSMiddleware, allow_origins=["*"])

router = Router(prefix="/api/v1")
db: dict[int, dict] = {}


class TodoCreate(BaseModel):
    title: str
    completed: bool = False


@router.get("/todos")
async def list_todos():
    return list(db.values())


@router.post("/todos", status_code=201)
async def create_todo(todo: TodoCreate):
    todo_id = len(db) + 1
    db[todo_id] = {"id": todo_id, **todo.model_dump()}
    return db[todo_id]


@router.get("/todos/{todo_id}")
async def get_todo(todo_id: int):
    if todo_id not in db:
        raise HTTPException(404, detail="Todo not found")
    return db[todo_id]


app.include_router(router)

if __name__ == "__main__":
    app.run(port=8000)
```

Run it:

```bash
python main.py                # or: rivex run main:app --reload
```

Then open:

- `http://127.0.0.1:8000/docs` — interactive Swagger UI
- `http://127.0.0.1:8000/redoc` — ReDoc reference
- `http://127.0.0.1:8000/openapi.json` — the OpenAPI 3.1 schema

A malformed body returns **422** automatically, with per-field detail — you
write no validation code.

## Core concepts

### Routing

Function routes, `Router` groups, and class-based `Controller`s all mix freely:

```python
from rivex import Controller, get, post

class UsersController(Controller):
    path = "/users"
    tags = ["users"]

    @get("/{user_id}")
    async def get_user(self, user_id: int):
        return {"id": user_id}

    @post("/", status_code=201)
    async def create_user(self):
        return {"ok": True}

app.include_controller(UsersController)
```

Decorators: `get`, `post`, `put`, `delete`, `patch`, `head`, `options`, plus
`@app.websocket(...)`. Name a route and build its URL with `app.url_for(...)`.

### Parameters & validation

Type annotations decide where each value comes from; markers add constraints:

```python
from rivex import Body, Header, Path, Query

@app.get("/products/{product_id}")
async def get_product(
    product_id: int = Path(..., ge=1),
    fields: str = Query("all"),
    api_key: str = Header(..., alias="X-API-Key"),
):
    return {"id": product_id, "fields": fields}
```

Use a Pydantic `BaseModel` or Rivex's own `Schema` for request bodies:

```python
from rivex import Schema, Field

class SignUp(Schema):
    email: str
    age: int = Field(ge=0, le=150)
```

### Responses

Return a `dict`/model for JSON, or an explicit response class:

```python
from rivex import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse

@app.get("/page")
async def page():
    return HTMLResponse("<h1>Hello</h1>")
```

Also available: `PlainTextResponse`, `EventSourceResponse` (SSE), `XMLResponse`,
and the `status` constants + `HTTPException` for errors.

### Dependency injection

```python
from rivex import Depends, Request

def current_user(request: Request):
    if not request.header("authorization"):
        raise HTTPException(401, detail="Missing token")
    return {"id": 1}

@app.get("/me")
async def me(user=Depends(current_user)):
    return user
```

Dependencies cache per request, nest arbitrarily, and support `scope="singleton"`.

### Middleware

```python
from rivex import CORSMiddleware, SecurityHeadersMiddleware, RateLimitMiddleware

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, rate=1000, per=3600.0)
app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"])
```

20+ built-ins: compression, sessions, CSRF, idempotency, trusted-host,
HTTPS-redirect, timeout, IP filter, request-id, access logs, and more.

### Security & auth

```python
from rivex import Depends, hash_password, verify_password
from rivex.jwt import JWTBearer, encode

auth = JWTBearer(secret="secret")

@app.get("/account")
async def account(claims: dict = Depends(auth)):
    return {"user": claims["sub"]}
```

Security schemes (`HTTPBearer`, `HTTPBasic`, `APIKeyHeader`, `OAuth2…`), guards,
throttling, Rust-backed password hashing, and a battery of validators
(`validate_email`, `luhn_check`, `sanitize_html`, …) are all included.

### WebSockets

```python
from rivex import WebSocket

@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    async for kind, payload in ws:
        await ws.send_text(f"echo: {payload}")
```

`rivex.ws.ConnectionManager` adds room-based broadcast.

### Background tasks & concurrency

```python
from rivex import BackgroundTasks, run_in_threadpool

@app.post("/signup", status_code=202)
async def signup(email: str, tasks: BackgroundTasks):
    tasks.add_task(send_welcome_email, email)
    return {"status": "accepted"}
```

Wrap blocking/CPU-bound work in `await run_in_threadpool(fn, ...)` so it doesn't
hold a Rust worker thread.

### High-performance JSON

```python
from rivex.gen import gen, F

@app.get("/items")
async def items():
    return gen.wrap("items", 10_000, id=F.index, name=F.fmt("Item {}"))
```

`gen` constructs large JSON arrays entirely in Rust — no intermediate Python
objects — for throughput plain list comprehensions can't match.

### Testing

```python
from rivex import TestClient

client = TestClient(app)

def test_get_todo():
    assert client.get("/api/v1/todos/1").status_code in (200, 404)
```

`TestClient` runs the full pipeline (middleware, DI, validation) in-process —
no server, no socket. It also supports `websocket_connect(...)`.

## The CLI

```bash
rivex run main:app --reload          # dev server with autoreload
rivex run main:app --workers 4       # production-style, SO_REUSEPORT workers
rivex routes main:app                # list every registered route
rivex version                        # print the installed version
rivex schemax …                      # Schemax IDL toolchain (needs the schemax pkg)
```

## Documentation

A complete, page-by-page guide lives in [`docs/`](docs/) — installation,
routing, parameters, dependency injection, middleware, security, websockets,
the `gen` JSON generator, OpenAPI, testing, observability (including the
`rivex_monitor` dashboard), deployment, and a one-page API reference. Start at
[`docs/README.md`](docs/README.md).

## Project layout

```text
rivex-python/
├── rivex/                 # the SDK package (applications, routing, params,
│                          #   responses, middleware, security, jwt, gen, …)
├── rivex_monitor/         # cross-language protocol monitoring dashboard
├── examples/              # runnable example apps (hello, todo_api, auth, …)
├── tests/                 # pytest suite (70+ integration/feature tests)
├── docs/                  # the full documentation guide
├── bench/                 # benchmark harness + reports
└── pyproject.toml
```

## Development

```bash
pip install -e ".[dev]"     # editable install with dev tooling
pytest                      # run the test suite
ruff check .                # lint
mypy rivex                  # type-check
```

## The Rivex ecosystem

Every Rivex SDK is a thin, idiomatic binding over the same **Rust core
(`rivex-core`)**, so routing, validation, and raw performance stay consistent
across languages.

| Component | Package / module | Language |
| --- | --- | --- |
| Core runtime | `rivex-core` | Rust |
| Python SDK | `rivex` | Python ≥ 3.10 |
| TypeScript / JavaScript SDK | `rivex` | TypeScript / Node |
| Go SDK | `github.com/shregar1/rivex-go` | Go |
| Ruby SDK | `rivex` | Ruby |
| CLI | `rivex-cli` | Python |

## Contributing

Contributions are welcome. Install the dev extra, add tests for any change, and
make sure `pytest`, `ruff check .`, and `mypy rivex` all pass before opening a
PR. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full workflow.

## License

Released under the [MIT License](LICENSE). © 2025–2026 Shreyansh Singh, Shivansh Singh.
