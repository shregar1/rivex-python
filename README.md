# Rivex Python SDK

[![PyPI](https://img.shields.io/pypi/v/rivex-py)](https://pypi.org/project/rivex-py/)
[![Python](https://img.shields.io/pypi/pyversions/rivex-py)](https://pypi.org/project/rivex-py/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/shregar1/rivex-python/actions/workflows/ci.yml/badge.svg)](https://github.com/shregar1/rivex-python/actions/workflows/ci.yml)

**A Rust-powered Python web framework with FastAPI-like ergonomics.** You write ordinary type-annotated Python handlers — a native Rust core (`rivex-core`) accepts connections, parses requests, encodes JSON, and drives your code on worker threads.

```python
from rivex import Rivex

app = Rivex(title="Hello API", version="1.0.0")

@app.get("/users/{user_id}")
async def get_user(user_id: int, verbose: bool = False):
    return {"id": user_id, "verbose": verbose}

app.run(host="0.0.0.0", port=8000)   # interactive docs at /docs
```

## Why Rivex

- **Familiar API** — decorator routes, `Depends()` injection, Pydantic models, auto-generated OpenAPI. The app class is also exported as `FastAPI` for drop-in muscle memory.
- **Rust core, not an ASGI shim** — the server, request parsing, JSON encoding, password hashing, JWT, and validators all run in Rust. You opt into the fast paths without leaving Python.
- **Batteries included** — 20+ production middleware, security schemes, JWT auth, guards, throttling, WebSockets, background tasks, caching, pagination, metrics, tracing, structured logging, health checks, and a monitoring dashboard.
- **Two validation engines** — Pydantic `BaseModel` or  lighter `Schema`. Interchangeable at the handler boundary.
- **Native JSON generation** — `rivex.gen` builds large JSON payloads entirely in Rust with no intermediate Python objects, for throughput plain list comprehensions can't match.

## Benchmarks

Cross-language world-bench on Azure D4s_v5 (4 vCPU, 16 GB) against Python web frameworks using `wrk` 4.2.0.

| Framework | Language | RPS (plaintext) | RPS (JSON) |
| --- | --- | --- | --- |
| **Rivex** | **Python** | **233,744** | **234,614** |
| Robyn | Python | 127,892 | 119,880 |
| starlette | Python | 49,225 | 48,747 |
| sanic | Python | 46,684 | 50,440 |
| fastapi | Python | 13,078 | 12,649 |

All results at 256 concurrent connections. p99 latency stays under 4ms for Rivex.

Global regions (Rivex Python, server-local: **235,808 RPS**, p99 3.38ms):

| Region | RPS | p99 |
| --- | --- | --- |
| Singapore | 5,952 | 174ms |
| Sweden | 6,193 | 164ms |
| India | 4,521 | 225ms |
| UAE | 4,077 | 251ms |

## Installation

```bash
pip install rivex
```

Optional extras:

```bash
pip install "rivex[dev]"       # pytest, httpx, mypy, ruff
pip install "rivex[admin]"     # admin dashboard
pip install "rivex[all]"       # everything
```

Verify:

```bash
rivex version
```

## Quickstart

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
app.run(port=8000)
```

Open: `http://127.0.0.1:8000/docs` (Swagger), `/redoc`, `/openapi.json`.

## Core concepts

### Routing

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

Decorators: `get`, `post`, `put`, `delete`, `patch`, `head`, `options`, `websocket`.

### Parameters & validation

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

Use Pydantic `BaseModel` or Rivex `Schema` for request bodies.

### Responses

```python
from rivex import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse

@app.get("/page")
async def page():
    return HTMLResponse("<h1>Hello</h1>")
```

Also: `PlainTextResponse`, `EventSourceResponse` (SSE), `XMLResponse`, `JSONResponse`, and `StreamingResponse`.

### Dependency injection

```python
from rivex import Depends, HTTPException, Request

def current_user(request: Request):
    if not request.header("authorization"):
        raise HTTPException(401, detail="Missing token")
    return {"id": 1}

@app.get("/me")
async def me(user=Depends(current_user)):
    return user
```

Dependencies cache per request, nest arbitrarily, and support `scope="singleton"`.

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

### Background tasks

```python
from rivex import BackgroundTasks

@app.post("/signup", status_code=202)
async def signup(email: str, tasks: BackgroundTasks):
    tasks.add_task(send_welcome_email, email)
    return {"status": "accepted"}
```

### Testing

```python
from rivex.testing import TestClient

client = TestClient(app)

def test_get_todo():
    assert client.get("/api/v1/todos/1").status_code in (200, 404)
```

`TestClient` runs the full pipeline (middleware, DI, validation) in-process — no server, no socket.

## CLI

```bash
rivex run main:app --reload         # dev server with autoreload
rivex run main:app --workers 4      # production with SO_REUSEPORT workers
rivex routes main:app               # list every route
rivex version                        # print version
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy rivex
```

## Rivex ecosystem

| Component | Package | Language |
| --- | --- | --- |
| Core runtime | `rivex-core` | Rust |
| Python SDK | `rivex` | Python >= 3.10 |
| TS/JavaScript SDK | `rivex` | TypeScript/Node |
| Go SDK | `github.com/shregar1/rivex-go` | Go |
| Ruby SDK | `rivex` | Ruby |
| CLI | `rivex-cli` | Python |

## License

MIT — see [LICENSE](LICENSE). (C) 2025-2026 Shreyansh Singh, Shivansh Singh.
