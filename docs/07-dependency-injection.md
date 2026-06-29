# Dependency Injection

Dependency injection lets you declare what a handler *needs* — the current user, a database session, validated pagination — and have Rivex supply it. Dependencies are resolved per request, cached within that request, and can depend on one another. This keeps handlers small and makes logic reusable and testable.

## Function dependencies

A dependency is any callable. Wrap it in `Depends()` as a parameter default; Rivex calls it (resolving *its* parameters the same way as a handler's) and passes the result in.

```python
from rivex import Depends, HTTPException, Request, Rivex

app = Rivex()


def current_user(request: Request):
    token = request.header("authorization", "")
    if not token.startswith("Bearer "):
        raise HTTPException(401, detail="Missing token")
    return {"id": 1, "name": "Ada"}


@app.get("/me")
async def me(user: dict = Depends(current_user)):
    return user
```

The dependency receives the same injection treatment as a handler — it can take path params, query params, the `Request`, or further sub-dependencies.

## Class dependencies

Subclass `Dependency` and implement `resolve()` for stateful or configurable dependencies. `resolve()` can be sync or async and receives injected parameters just like a function dependency.

```python
from rivex import Dependency, Request


class CurrentUser(Dependency):
    def resolve(self, request: Request) -> dict:
        token = request.header("authorization", "").removeprefix("Bearer ")
        if not token:
            raise HTTPException(401, detail="Missing token")
        return {"id": 1, "name": "Ada"}


@app.get("/profile")
async def profile(user: dict = Depends(CurrentUser)):
    return user
```

A dependency can pull from several sources at once:

```python
class AuditContext(Dependency):
    def resolve(self, item_id: int, request: Request, debug: bool = False):
        return {"item_id": item_id, "url": request.url, "debug": debug}


@app.get("/items/{item_id}")
async def read_item(ctx = Depends(AuditContext)):
    # item_id ← path, debug ← query, request ← injected
    return ctx
```

## Nested dependencies

Dependencies compose. Rivex resolves the graph depth-first, so a dependency can itself depend on others:

```python
def get_db():
    return database_handle


def get_repo(db = Depends(get_db)):
    return UserRepository(db)


@app.get("/users/{user_id}")
async def get_user(user_id: int, repo = Depends(get_repo)):
    return repo.find(user_id)
```

## Caching within a request

By default a dependency is **cached per request** (`use_cache=True`): if two places in the graph depend on the same callable, it runs once and the result is shared. Disable this when you need a fresh value each time:

```python
@app.get("/report")
async def report(
    a = Depends(expensive),                    # computed once...
    b = Depends(expensive),                    # ...reused here
    c = Depends(expensive, use_cache=False),   # forced to recompute
):
    ...
```

## Singleton scope

Pass `scope="singleton"` to resolve a dependency once for the lifetime of the process and reuse it across all requests — ideal for connection pools and other shared resources:

```python
@app.get("/status")
async def status(pool = Depends(SharedPool, scope="singleton")):
    return {"open": pool.is_open()}
```

## Validation and errors

Because dependencies resolve their own parameters, the same validation rules apply: a missing required query/path value or a failed type coercion inside a dependency produces a **422**. A dependency may also raise `HTTPException` directly (e.g. `401` for a bad token), which becomes the response.

## A reusable pattern: auth + pagination

```python
from dataclasses import dataclass


@dataclass
class Page:
    limit: int
    offset: int


def pagination(limit: int = 20, offset: int = 0) -> Page:
    return Page(min(limit, 100), max(offset, 0))


@app.get("/articles")
async def list_articles(
    user: dict = Depends(current_user),
    page: Page = Depends(pagination),
):
    return {"user": user["id"], "limit": page.limit, "offset": page.offset}
```

Both dependencies are declared once and reused across every endpoint that needs them — and each is trivial to swap out in tests.

## Next

**Middleware** covers cross-cutting behaviour that wraps *every* request, complementing per-handler dependencies.
