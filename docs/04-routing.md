# Routing

Routing maps an HTTP method and URL path to a handler function. Rivex offers three styles — plain function routes, `Router` groups, and class-based `Controller`s — that you can mix freely.

## Function routes

Decorate a handler with an HTTP-method decorator on the app:

```python
from rivex import Rivex

app = Rivex()


@app.get("/ping")
async def ping():
    return {"pong": True}


@app.post("/items", status_code=201)
async def create_item():
    return {"created": True}
```

Available decorators: `get`, `post`, `put`, `delete`, `patch`, `head`, `options`. There is also a generic `@app.route(path, methods=[...])`.

### Decorator options

Every route decorator accepts keyword arguments that shape behaviour and documentation:

| Argument | Purpose |
| --- | --- |
| `status_code` | Default success status (default `200`) |
| `tags` | OpenAPI grouping tags |
| `summary`, `description` | Human-readable docs |
| `operation_id` | Explicit OpenAPI operation id |
| `response_model` | Model used to filter/serialize the response |
| `deprecated` | Mark the route deprecated in the schema |
| `include_in_schema` | Set `False` to hide from OpenAPI |
| `responses` | Extra documented status codes |
| `name` | Route name for reverse lookup with `url_for()` |

```python
@app.get(
    "/users",
    tags=["users"],
    summary="List users",
    name="list_users",
)
async def list_users():
    return []
```

## Path and query parameters

Path segments in `{braces}` become handler arguments. The type annotation drives conversion and validation; arguments **without** a default are required query parameters, and arguments **with** a default are optional.

```python
@app.get("/users/{user_id}/posts/{post_id}")
async def get_post(user_id: int, post_id: int, draft: bool = False):
    # GET /users/7/posts/3?draft=true
    return {"user_id": user_id, "post_id": post_id, "draft": draft}
```

- `user_id` and `post_id` come from the path and must be integers (a non-integer yields **422**).
- `draft` is a query parameter, optional, defaulting to `False`.

For aliases, bounds, and other constraints, use the explicit `Path()`/`Query()` markers covered in **Parameters & Validation**.

## Routers

A `Router` (aliased `APIRouter`) collects routes under a common prefix and tag set, then is mounted onto the app — ideal for splitting a large API across modules.

```python
from rivex import Router

users = Router(prefix="/users", tags=["users"])


@users.get("")
async def list_users():
    return []


@users.get("/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id}


app.include_router(users)
```

`include_router(router, prefix="", tags=[...])` can add a further prefix or tags at mount time. Routers can include other routers for deep nesting.

## Controllers

A `Controller` is a class whose methods are routes — Litestar-style. Use it when a group of endpoints shares a prefix, tags, or instance state. Decorate methods with the standalone `get`/`post`/etc. decorators imported from `rivex`.

```python
from rivex import Controller, Rivex, get, post


class UsersController(Controller):
    path = "/users"
    tags = ["users"]

    @get("/{user_id}")
    async def get_user(self, user_id: int):
        return {"id": user_id}

    @post("/", status_code=201)
    async def create_user(self):
        return {"ok": True}


app = Rivex()
app.include_controller(UsersController)
```

Controllers can also be added through `include_router()`, and can be included as **instances** when they need constructor state:

```python
class ReportController(Controller):
    path = "/reports"

    def __init__(self, store):
        self.store = store

    @get("/summary")
    async def summary(self):
        return self.store.summary()


app.include_controller(ReportController(store=my_store))
```

## Route groups

`app.group(...)` (and `router.group(...)`) opens a lightweight scope for a handful of routes that share a prefix/tags without defining a separate `Router` object:

```python
group = app.group(prefix="/admin", tags=["admin"])


@group.get("/stats")
async def stats():
    return {"users": 100}
```

## Reverse URLs with `url_for`

Give a route a `name` and build its URL from anywhere — handy for redirects and links:

```python
@app.get("/items/{item_id}", name="get_item")
async def get_item(item_id: int):
    return {"id": item_id}


app.url_for("get_item", item_id=42)   # "/items/42"
```

## Inspect your routes

The CLI prints every registered route — a quick sanity check:

```bash
rivex routes main:app
```

## Next

Continue to **Parameters & Validation** to control exactly how inputs are parsed, or **Requests & Responses** for the full I/O surface.
