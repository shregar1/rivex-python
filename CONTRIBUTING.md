# Contributing to Rivex Python SDK

Thank you for your interest in contributing to Rivex! This guide covers
the Python SDK — the user-facing framework layer built on the Rust runtime.

## Prerequisites

- **Python** 3.10+
- **Rust** toolchain (the Rust core is compiled into the `rivex` wheel)
- **maturin** (`pip install maturin`)
- The sibling **core repo** checked out as `../rivex-core` (the wheel is built against it — see
  `[tool.maturin] manifest-path` in `pyproject.toml`).

## Repository Layout

```
rivex/
  __init__.py          # Public API exports
  applications.py      # Rivex/FastAPI app class
  routing.py           # Router, RouteRecord
  _injection.py        # Dependency injection, handler wrapping
  middleware.py         # CORS, GZip, RequestId, TrustedHost
  openapi.py           # OpenAPI 3.1 spec generation
  requests.py          # Request class
  responses.py         # Response classes (JSON, HTML, Redirect, Streaming)
  dependencies.py      # Depends class
  datastructures.py    # Headers
  exceptions.py        # HTTPException
  background.py        # BackgroundTask, BackgroundTasks
  uploads.py           # UploadFile, File, Form
  status.py            # HTTP status code constants
tests/
  test_application.py  # App initialization and routing
  test_routing.py      # Router and route records
  test_depends.py      # Dependency injection
  test_injection.py    # Handler wrapping and response normalization
  test_openapi.py      # OpenAPI generation
  test_integration.py  # Full-stack integration tests
examples/
  hello.py             # Basic hello world
  todo_api.py          # CRUD API example
```

## Getting Started

```bash
# Clone the repository
git clone https://github.com/shregar1/rivex-python.git
cd rivex-python

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Build & install the rivex extension (compiles the Rust core from the sibling
# ../rivex-core into this package — no separate rivex-core install)
maturin develop --release

# Install the pure-Python dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## Development Workflow

1. **Create a branch** from `main`
2. **Write tests** for your changes
3. **Run the full check suite**:
   ```bash
   ruff format --check .
   ruff check .
   pytest tests/ -v
   ```
4. **Open a pull request** targeting `main`

## Writing Tests

- Unit tests go in `tests/test_*.py` files matching the module being tested
- Integration tests go in `tests/test_integration.py`
- Use `pytest` conventions (functions or classes prefixed with `test_`/`Test`)
- Use `@pytest.mark.asyncio` for async tests (with `asyncio_mode = "strict"`)
- Tests should NOT require a running server — test the Python layer directly

```python
def test_my_feature():
    app = Rivex()

    @app.get("/test")
    async def handler():
        return {"result": "ok"}

    assert len(app._routes) == 1
```

## Commit Messages

```
fix(middleware): strip Content-Length after gzip compression
feat(injection): add support for Form() parameters
test(openapi): add tests for nested router tag merging
```

## Versioning

This project uses [Semantic Versioning](https://semver.org/).
Version is set in `pyproject.toml` under `[project] version`.
When bumping, update `pyproject.toml`, `rivex/__init__.py`, and `CHANGELOG.md`.

## Code Style

- Format with `ruff format`
- Lint with `ruff check`
- Type hints on all public function signatures
- Docstrings on public classes and functions
- Async by default — use `async def` for handlers and middleware

## CI

GitHub Actions runs on every push and PR:

| Check | Command |
|-------|---------|
| Format | `ruff format --check .` |
| Lint | `ruff check .` |
| Type check | `mypy rivex/` |
| Test | `pytest tests/ -v` |
| Build | `python -m build` |

All checks must pass before merging.
