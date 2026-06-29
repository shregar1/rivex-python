# OpenAPI & Docs

Rivex generates an **OpenAPI 3.1** schema from your route signatures, parameter markers, and models — and serves two interactive UIs from it. You get accurate API docs for free, and they stay in sync because they're derived from the code.

## The default endpoints

A fresh `Rivex()` app serves:

| URL | What it is |
| --- | --- |
| `/openapi.json` | The raw OpenAPI 3.1 schema |
| `/docs` | Swagger UI — try requests in the browser |
| `/redoc` | ReDoc — clean three-pane reference |

Open `http://127.0.0.1:8000/docs` after starting any app.

## Describing your API

Constructor arguments populate the schema's top-level metadata:

```python
from rivex import Rivex

app = Rivex(
    title="Payments API",
    version="2.3.0",
    description="Process and refund payments.",
    openapi_tags=[
        {"name": "charges", "description": "Create and capture charges"},
        {"name": "refunds", "description": "Issue refunds"},
    ],
    servers=[
        {"url": "https://api.example.com", "description": "Production"},
        {"url": "https://staging.example.com", "description": "Staging"},
    ],
    contact={"name": "API Support", "email": "support@example.com"},
    license_info={"name": "MIT"},
    terms_of_service="https://example.com/terms",
)
```

## Documenting routes

Route decorator options flow straight into the operation object:

```python
@app.get(
    "/charges/{charge_id}",
    tags=["charges"],
    summary="Retrieve a charge",
    description="Fetch a single charge by its id.",
    operation_id="get_charge",
    responses={404: {"description": "Charge not found"}},
)
async def get_charge(charge_id: str):
    ...
```

- **Models** used as bodies and `response_model` are emitted as reusable schema components.
- **Parameter markers** contribute `description`, `examples`, constraints, and `deprecated` flags.
- **Security schemes** (from *Security & Authentication*) appear under `securitySchemes`, enabling the **Authorize** button in Swagger UI.

## Hiding and customizing

Keep an endpoint out of the schema:

```python
@app.get("/internal/metrics", include_in_schema=False)
async def internal_metrics():
    ...
```

Relocate or disable the UIs via constructor arguments — set any to `None` to turn it off:

```python
app = Rivex(
    openapi_url="/api/openapi.json",   # move the schema
    docs_url="/api/docs",              # move Swagger UI
    redoc_url=None,                    # disable ReDoc
)
```

Setting `openapi_url=None` disables the schema and both UIs entirely — useful for locked-down internal services.

## Branding

`logo_url` and `favicon_url` let you brand the docs pages:

```python
app = Rivex(
    title="Acme API",
    logo_url="https://acme.example.com/logo.svg",
    favicon_url="https://acme.example.com/favicon.ico",
)
```

## Next

**Testing** shows how to exercise all of this in-process, without starting a server.
