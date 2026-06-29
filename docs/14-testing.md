# Testing

Rivex provides multiple testing strategies — an in-process `TestClient` that runs the full pipeline
(middleware, dependency injection, validation, exception handlers, lifespan), an `ASGIAdapter` that
works with any ASGI-capable transport (e.g., `httpx.ASGITransport`), and a set of reusable pytest
fixtures for databases, caches, and external HTTP services.

---

## TestClient

`TestClient` runs your app in-process — no socket, no running server. A test exercises the
same code path as a real request but fast and deterministic.

```python
from rivex import Rivex, TestClient

app = Rivex()


@app.get("/items/{item_id}")
async def get_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}


client = TestClient(app)


def test_get_item():
    resp = client.get("/items/42", params={"q": "hello"})
    assert resp.status_code == 200
    assert resp.json() == {"item_id": 42, "q": "hello"}
```

### Client surface

| Call | Notes |
| --- | --- |
| `client.get(url, **kw)` | also `post`, `put`, `patch`, `delete` |
| `params={...}` | query string |
| `json={...}` | JSON body + `Content-Type: application/json` |
| `data={...}` | form-urlencoded body |
| `files={...}` | multipart upload |
| `headers={...}` | request headers |
| `content=b"..."` | raw body bytes/string |

The response object exposes `status_code`, `headers`, `.json()`, `.text`, and `.content`.

### Posting JSON and forms

```python
def test_create():
    resp = client.post("/items", json={"name": "Widget", "price": 9.99})
    assert resp.status_code == 201


def test_login_form():
    resp = client.post("/token", data={"username": "ada", "password": "pw"})
    assert resp.status_code == 200
```

### Validation paths

Asserting on automatic 422 responses is a good habit:

```python
def test_bad_type_is_422():
    resp = client.get("/items/not-a-number")
    assert resp.status_code == 422
```

### Lifespan in tests

Use the client as a context manager to run `startup`/`shutdown` hooks (DB pools, caches, etc.):

```python
def test_with_lifespan():
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
    # shutdown hooks have now run
```

### WebSockets

```python
def test_ws_echo():
    with client.websocket_connect("/ws") as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "echo: ping"
```

---

## ASGITransport (httpx)

For advanced scenarios — custom middleware stacks, streaming responses, or when you need to
combine Rivex with other ASGI apps — use `httpx.ASGITransport` directly:

```python
import httpx
from rivex import Rivex
from rivex.asgi import ASGIAdapter

app = Rivex()

@app.get("/hello")
async def hello():
    return {"message": "Hello, world!"}

adapter = ASGIAdapter(app)

async def test_via_asgi_transport():
    transport = httpx.ASGITransport(app=adapter)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/hello")
        assert resp.status_code == 200
        assert resp.json() == {"message": "Hello, world!"}
```

This path runs the ASGI adapter directly and supports everything `httpx` offers —
parallel requests, connection pooling, timeouts, and streaming.

The `TestClient` is faster for most use cases (it avoids the ASGI event-loop overhead),
but the ASGITransport path is useful when you already have httpx-based test infrastructure.

---

## Mocking Dependencies

Rivex uses `app.dependency_overrides` to let you swap out dependencies during tests —
no monkey-patching required. This is the same pattern FastAPI popularized.

### Override per callable

```python
from rivex import Rivex, TestClient
from rivex.dependencies import Depends

app = Rivex()


# The real dependency
async def get_db() -> str:
    return "real-db"


@app.get("/items")
async def list_items(db: str = Depends(get_db)):
    return {"db": db, "items": []}


# Test override
async def mock_db() -> str:
    return "mock-db"


app.dependency_overrides[get_db] = mock_db

client = TestClient(app)


def test_list_items_uses_mock_db():
    resp = client.get("/items")
    assert resp.json()["db"] == "mock-db"
```

### Convenience helpers

`app.override_dependency(original, mock)` and `app.clear_overrides()` make setup/teardown
cleaner:

```python
def test_something():
    app.override_dependency(get_db, mock_db)
    resp = client.get("/items")
    app.clear_overrides()  # restore all originals
```

### Context-manager override

`app.override_scope(overrides)` temporarily replaces overrides for a block:

```python
with app.override_scope({get_db: mock_db}):
    resp = client.get("/items")
    assert resp.json()["db"] == "mock-db"
# overrides restored after block
```

---

## Pytest Fixtures (built-in)

Rivex ships with reusable pytest fixtures in `rivex.testing_fixtures` for common
testing patterns:

```python
import pytest
from rivex.testing_fixtures import app, client, db, http_mock
```

### Available fixtures

| Fixture | Scope | What it provides |
| --- | --- | --- |
| `app` | `function` | A fresh `Rivex()` instance |
| `client` | `function` | A `TestClient` wrapping the `app` fixture |
| `db`
{:raw}` 📝 "`db`" → `rivex.db.DatabaseRegistry` | `function` | An isolated SQLite in-memory database |
| `http_mock` | `function` | An `respx`-based HTTP mock (intercepts `httpx`/`httplib`) |
| `redis_mock` | `function` | A `fakeredis`-based in-memory Redis mock |

### Example

```python
from rivex.testing_fixtures import app, client


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
```

### Customising the app fixture

The `app` fixture accepts optional parameters via `pytest.mark`:

```python
import pytest


@pytest.mark.rivex_app(template_dir="tests/templates", liveness_url="/healthz")
def test_with_options(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
```

### Using the DB fixture

```python
from rivex.testing_fixtures import app, client, db


def test_db_query(client, db):
    # db is a DatabaseRegistry with an in-memory SQLite pool
    db.configure("default", url="sqlite:///:memory:")
    resp = client.get("/users")
    assert resp.status_code == 200
```

### Using the HTTP mock

```python
from rivex.testing_fixtures import app, client, http_mock


def test_external_api(client, http_mock):
    http_mock.get("https://api.example.com/data").respond(
        status_code=200, json={"key": "value"}
    )
    resp = client.get("/proxy")
    assert resp.json() == {"key": "value"}
```

---

## Dependency Override Cheatsheet

| Use case | Pattern |
| --- | --- |
| Override one dependency | `app.dependency_overrides[original] = mock` |
| Override with convenience | `app.override_dependency(original, mock)` |
| Restore all originals | `app.clear_overrides()` |
| Temporary override (context) | `with app.override_scope({original: mock}):` |

---

## Writing your own fixtures

A typical pattern is to factor the app setup into a `conftest.py`:

```python
# tests/conftest.py
import pytest
from rivex import Rivex, TestClient
from myapp import app as real_app


@pytest.fixture
def app():
    return real_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def authed_client(client):
    """Client with a pre-authenticated session."""
    # … set up auth header, JWT, etc.
    return client
```

---

## Coverage

Run tests with coverage via the CLI:

```bash
rivex test --cov=myapp tests/
```

This is equivalent to:

```bash
pytest --cov=myapp --cov-report=term-missing tests/
```

Additional flags (e.g., `--cov-report=html`) are passed straight through to pytest:

```bash
rivex test --cov=myapp --cov-report=html tests/
```

Install the dev extra to get all testing dependencies:

```bash
pip install "rivex[dev]"
```

---

## Next

**Observability** covers metrics, tracing, structured logging, and health checks for production.
