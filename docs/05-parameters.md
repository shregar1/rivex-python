# Parameters & Validation

Rivex reads your handler's signature to decide where each argument comes from — path, query string, headers, cookies, form fields, or the JSON body — and validates it before your code runs. When a value is missing or the wrong type, Rivex responds with **422 Unprocessable Entity** and a structured error; you never write that boilerplate.

## Implicit rules

Without any markers, Rivex applies sensible defaults:

- A name that matches a `{path}` segment → **path parameter**.
- A scalar argument (`int`, `str`, `bool`, …) not in the path → **query parameter**.
- A Pydantic/`Schema` model argument → the **JSON request body**.
- A `Request`, `WebSocket`, `BackgroundTasks`, or `Depends(...)` argument → injected, not read from the request.

```python
@app.get("/search/{category}")
async def search(category: str, q: str, limit: int = 20):
    # category ← path, q ← required query, limit ← optional query
    return {"category": category, "q": q, "limit": limit}
```

## Explicit parameter markers

For constraints, aliases, and documentation, import the markers and use them as defaults:

```python
from rivex import Body, Cookie, Header, Path, Query
```

| Marker | Source |
| --- | --- |
| `Path(...)` | URL path segment |
| `Query(...)` | Query string |
| `Header(...)` | Request header |
| `Cookie(...)` | Cookie |
| `Body(...)` | (Part of) the request body |

Pass `...` (Ellipsis) to mark a parameter **required**, or a value to give it a default.

```python
@app.get("/products/{product_id}")
async def get_product(
    product_id: int = Path(..., ge=1, description="Positive product id"),
    fields: str = Query("all", description="Comma-separated field list"),
    api_key: str = Header(..., alias="X-API-Key"),
    session: str | None = Cookie(None),
):
    return {"id": product_id, "fields": fields}
```

### Validation constraints

The markers accept the same constraints as Pydantic `Field`:

- Numbers: `gt`, `ge`, `lt`, `le`, `multiple_of`
- Strings/collections: `min_length`, `max_length`, `pattern`
- Docs/metadata: `title`, `description`, `examples`, `deprecated`
- Mapping: `alias` (read from a different name), `include_in_schema`

A header name like `X-API-Key` is awkward as a Python identifier, so use `alias`. Header lookups are case-insensitive.

## Request bodies

The most common body is a model. Declare it as a parameter and Rivex parses and validates the JSON for you:

```python
from pydantic import BaseModel


class ItemCreate(BaseModel):
    name: str
    price: float
    tags: list[str] = []


@app.post("/items", status_code=201)
async def create_item(item: ItemCreate):
    return item            # serialized back to JSON
```

### Scalar and multiple bodies

Use `Body()` to pull a raw scalar from the JSON body, or to combine several body fields:

```python
@app.post("/discount")
async def discount(
    percent: float = Body(..., ge=0, le=100),
    reason: str = Body("seasonal"),
):
    # Expects: {"percent": 15, "reason": "launch"}
    return {"percent": percent, "reason": reason}
```

## Two validation engines

Rivex accepts **Pydantic `BaseModel`** and its own **`Schema`** interchangeably — it detects either by duck typing. `Schema` is a thinner layer over `pydantic-core` for when you don't need the full `BaseModel` surface.

```python
from rivex import Schema, Field


class User(Schema):
    id: int
    name: str = Field(min_length=1, max_length=100)
    email: str
    age: int = Field(ge=0, le=150)
    is_active: bool = True

    model_config = {"extra": "forbid"}   # reject unknown fields
```

`Schema` supports the Pydantic v2 essentials: `Field(...)` constraints and aliases, nested models, `Optional`/unions, enums, dates/UUIDs/Decimals, and the `@field_validator`, `@model_validator`, `@computed_field`, and `@field_serializer` decorators.

```python
from pydantic import field_validator


class Signup(Schema):
    email: str
    age: int

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.strip().lower()
```

Validate and serialize with the familiar methods:

```python
u = User.model_validate({"id": 1, "name": "Ada", "email": "ada@x.io", "age": 36})
u.model_dump()                 # → dict
u.model_dump(exclude_none=True)
u.model_dump_json(indent=2)    # → JSON string
```

Mix and match per route — a `Schema` body in one handler, a `BaseModel` body in another, both work.

## What triggers a 422

Rivex returns **422 Unprocessable Entity** when:

- a required path/query/header/cookie/body value is missing,
- a value can't be coerced to its annotated type (`/items/abc` for `item_id: int`),
- a constraint fails (`ge`, `max_length`, `pattern`, a custom validator),
- the JSON body is malformed.

The response body identifies the offending location and reason, so clients can correct the request.

## Next

See **Requests & Responses** for direct access to the raw request and for returning custom responses.
