# Rivex Python SDK — Examples

Each file is a standalone module. From the repo root:

```sh
python examples/hello.py
```

| Example | What it shows |
| --- | --- |
| `hello.py` | Minimal app: routing, path params, query params, type-annotated handlers. |
| `todo_api.py` | CRUD with `Router`, `CORSMiddleware`, `HTTPException`, Pydantic models. |
| `request_features.py` | Dependency injection, custom middleware, file uploads, forms. |
| `auth_bearer.py` | `HTTPBearer` security helper guarding protected routes. |
| `background_tasks.py` | `BackgroundTasks` parameter injected into the handler. |
| `middleware_chain.py` | Stacking custom + built-in middleware (timing, counter, request id, CORS). |
| `testing_demo.py` | Using `TestClient` to exercise an app without starting a server. |

Examples bind to `127.0.0.1:8000` by default. Stop with Ctrl+C.
