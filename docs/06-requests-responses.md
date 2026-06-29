# Requests & Responses

Most handlers just return a `dict` or a model and let Rivex serialize it. When you need more control — reading raw input, streaming, files, redirects, custom headers, or cookies — use the `Request` object and the response classes.

## The Request object

Add a `request: Request` parameter and Rivex injects the current request:

```python
from rivex import Request, Rivex

app = Rivex()


@app.post("/echo")
async def echo(request: Request):
    data = await request.json()
    return {
        "method": request.method,
        "path": request.path,
        "url": request.url,
        "auth": request.header("authorization"),
        "q": request.query_params.get("q"),
        "client": request.client.host,
        "body": data,
    }
```

### Common members

| Member | Description |
| --- | --- |
| `request.method` | HTTP method string |
| `request.path` | Path without the query string |
| `request.url` | Full URL including query string |
| `request.base_url` | Scheme + host (honours `X-Forwarded-Proto`) |
| `request.headers` | Case-insensitive header mapping |
| `request.header(name, default=None)` | Single header lookup |
| `request.query_params` | Parsed query parameters |
| `request.cookies` | Parsed cookies |
| `request.content_type` | The `Content-Type` value |
| `request.client` | Client `host` / `port` |
| `request.state` | Per-request scratch space for middleware |

### Reading the body

| Call | Returns |
| --- | --- |
| `await request.json()` | Parsed JSON (async, FastAPI-style) |
| `request.body()` | Raw `bytes` |
| `request.text()` | Body decoded as UTF-8 |
| `request.form()` | Parsed form fields |
| `request.stream()` | Async iterator of body chunks |

## Returning responses

### Automatic JSON

Returning a `dict`, `list`, Pydantic model, or `Schema` produces a JSON response using the route's `status_code`:

```python
@app.get("/user", status_code=200)
async def user():
    return {"id": 1, "name": "Ada"}
```

### Explicit response classes

Import what you need from `rivex`:

```python
from rivex import (
    JSONResponse, HTMLResponse, PlainTextResponse, RedirectResponse,
    StreamingResponse, EventSourceResponse, FileResponse, XMLResponse, Response,
)
```

| Class | Media type | Use for |
| --- | --- | --- |
| `JSONResponse` | `application/json` | JSON with custom status/headers |
| `HTMLResponse` | `text/html` | Rendered HTML |
| `PlainTextResponse` | `text/plain` | Plain text |
| `RedirectResponse` | — | 3xx redirects (default `307`) |
| `StreamingResponse` | configurable | Chunked/streamed bodies |
| `EventSourceResponse` | `text/event-stream` | Server-Sent Events |
| `FileResponse` | auto-detected | Serving a file from disk |
| `XMLResponse` | `application/xml` | XML payloads |
| `Response` | configurable | Full manual control |

```python
@app.get("/page")
async def page():
    return HTMLResponse("<h1>Hello</h1>")


@app.get("/old")
async def old():
    return RedirectResponse("/new", status_code=301)


@app.get("/report.pdf")
async def report():
    return FileResponse("./reports/q3.pdf", filename="q3.pdf")  # triggers download
```

### Streaming and Server-Sent Events

`StreamingResponse` accepts a sync or async iterable of `str`/`bytes`:

```python
async def numbers():
    for i in range(10):
        yield f"chunk {i}\n"


@app.get("/stream")
async def stream():
    return StreamingResponse(numbers(), media_type="text/plain")
```

For SSE, `EventSourceResponse` sets the right headers and provides an event formatter:

```python
@app.get("/events")
async def events():
    async def gen():
        for i in range(5):
            yield EventSourceResponse.format_event(data=f"tick {i}", event="update", id=str(i))
    return EventSourceResponse(gen())
```

### Headers and cookies

`Response` (and its subclasses) accept `headers=` and provide cookie helpers:

```python
@app.post("/login")
async def login():
    resp = JSONResponse({"ok": True})
    resp.set_cookie("session", "abc123", max_age=3600, httponly=True, secure=True, samesite="strict")
    return resp


@app.post("/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("session")
    return resp
```

## Errors

Raise `HTTPException` to short-circuit with an error status:

```python
from rivex import HTTPException, status


@app.get("/items/{item_id}")
async def get_item(item_id: int):
    if item_id not in db:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    return db[item_id]
```

`status` exposes named constants (`status.HTTP_201_CREATED`, `status.HTTP_409_CONFLICT`, …). For RFC 7807 problem responses, see **Observability**'s companion helpers in `rivex.problem`.

### Custom exception handlers

Map your own exceptions to responses:

```python
@app.exception_handler(ValueError)
async def on_value_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)
```

## Next

**Dependency Injection** shows how to factor shared logic — auth, DB sessions, pagination — out of individual handlers.
