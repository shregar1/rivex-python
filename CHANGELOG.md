# Changelog

All notable changes to this project will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.3] - 2026-07-10

### Fixed
- **Boot crash for CORS-enabled apps: `TypeError: argument 'host':
  'NoneType' object cannot be converted to 'PyString'`.** In 0.2.2 the
  CORS-preflight registration loop in
  `Rivex._drive_rust_server` reused the name `host` for the per-route
  host constraint (`host = path_hosts.get(path)`), shadowing the
  method's server bind-address parameter. When the last registered
  path had no host constraint — the common case — the final
  `server.run(host, port)` received `None` and every CORS-enabled app
  with routes crashed at startup. The loop local is now `route_host`,
  and `tests/test_cors_preflight_host_regression.py` pins the fix.
- **`Body()` with a DTO type hint now returns a validated DTO instance**
  instead of the raw JSON dict. Previously `payload: MyDto = Body()`
  passed the parsed JSON straight through and `payload.field` raised
  `AttributeError: 'dict' object has no attribute 'field'`. The
  parameter source now routes through the body-coercion layer
  (`rivex._bodies.coerce_body`) so every supported backend — pydantic,
  schemax, marshmallow, dataclass, attrs, msgspec, … — works uniformly
  whether the user writes `payload: MyDto` or `payload: MyDto = Body()`.
- **`int | None = Query(ge=…)` now coerces before validating.** Optional
  numeric query params with bound constraints used to raise
  `TypeError: '<' not supported between instances of 'str' and 'int'`
  because the raw query string was compared against the numeric bound
  before `int()` ran. `_coerce` now peels `X | None` / `Optional[X]` to
  `X` and the `Query`/`Header`/`Cookie`/`Path` extractors coerce
  consistently. The required-int path is unchanged.
- **CORS preflight under `allow_credentials=True` no longer ships
  `Access-Control-Allow-Methods: *` / `Access-Control-Allow-Headers: *`.**
  The CORS spec forbids these wildcards when credentials are sent;
  Chrome silently rejects the preflight while `curl` works fine —
  hiding the breakage from server logs. `CORSMiddleware` now warns at
  init AND auto-expands `*` per-request (echoes the browser's
  `Access-Control-Request-Method` / `Access-Control-Request-Headers`
  on preflight, or falls back to a safe default).
- **`POST` handlers with no body parameter cleanly accept empty
  bodies** (no change for handlers that *have* a body parameter).
  Required `payload: dict` annotations with empty bodies now return a
  clean `422 Field required` instead of crashing the codegen wrapper
  with a 500.

### Added
- **`rivex.context.RequestContextMiddleware`** — populate a
  `contextvars.ContextVar` with the request's `method`, `path`, `ip`,
  `user_agent`, and `request_id` so deep callers (audit / usage /
  structured-log utilities) can read `current_user_id()`,
  `current_ip()`, `current_user_agent()` without threading them
  through every input dataclass. Auth middleware calls `bind_user(id)`
  to fill in `user_id`; apps stamp arbitrary tags with
  `bind_extra(**kwargs)`. Per-task scoped via `contextvars` — concurrent
  requests can't see each other's context.
- **`rivex.authenticated` / `rivex.admin_only` decorators** — gate a
  handler on a user-supplied resolver:

  ```python
  set_user_resolver(my_resolve_session)

  @post("/widgets/{id}/archive")
  @authenticated
  async def archive(self, request: Request, id: int = Path()):
      user = current_user()  # full object stashed via the decorator
      ...
  ```

  The decorator runs the resolver before the handler body, raises 401
  if it returns `None`, and (with `role="admin"` or `@admin_only`)
  raises 403 on role mismatch. The resolved user is stashed in
  `request_context().extras["user"]` so the handler doesn't have to
  refetch it.

- **`MultipartBody`** — an alias for `Form` whose name reads more
  naturally in the canonical "metadata-DTO + binary file" recipe:

  ```python
  async def upload_model(
      payload: CreateModel = MultipartBody(),
      file: UploadFile = File(),
  ):
      ...
  ```

  The handler receives a validated DTO from the multipart text fields
  *and* the binary upload as an `UploadFile` — no base64, no
  JSON-in-multipart hack. The Pydantic backend ignores the binary
  field naturally; the `File()` slot picks it up via the normal
  `_extract_file` path.
- **Cross-language platform metrics (`rivex_monitor`)** — per-protocol
  monitoring (HTTP, WebSocket, WebRTC, gRPC) backed by a lock-free Rust
  atomic store (`rivex-http::platform_metrics`) with EWMA p50/p95/p99
  latency quantiles. Exposed to Python via `PyPlatformMetrics` (PyO3),
  to Node/JS via NAPI (`rivex-napi`), and to Go/Ruby via C FFI
  (`rivex-ffi`). The `rivex_monitor` Python package implements a
  dual-write architecture (Rust atomic counters + Python in-memory dict)
  with transparent fallback when the native extension is unavailable.
  Six admin dashboard partials (`monitor_http`, `monitor_ws`,
  `monitor_webrtc`, `monitor_grpc`, `monitor_adapters`,
  `monitor_health`) render live data from the shared store. 396 total
  tests (157 Rust + 239 Python), 0 failures.

### Added
- **`RivexAsyncServer` (mode `async` / `auto`)** — the bundled Rust
  `hyper+Tokio` engine is now the default and is exposed as
  `app.run_async()`. It supports HTTP/1.1 + HTTP/2 with auto-negotiation,
  streaming responses, and WebSocket upgrades on the same listener.
- **`RivexSyncServer` (mode `sync`)** — the std::thread + httparse engine
  is now actually wired to `app.run_sync()` (it was previously a no-op
  alias of the async path). It has lower per-request latency on pure-CPU
  handlers at the cost of streaming, HTTP/2 and WebSockets.
- **`Rivex.run(mode=...)`** — single entry point for engine selection.
  `mode` accepts `auto` (default), `async`, `sync`, or `asgi` (uvicorn
  fallback for FastAPI/Starlette compatibility).
- **`Rivex.add_const_route(method, path, status, body, headers)`** —
  register a *pre-baked* response for a static (no path parameters)
  route. The response is served without touching the matchit trie, the
  Python worker pool, or even the async runtime. Same idea as Robyn's
  `ConstRouter`. Available on all three engines (`async`, `sync`, `asgi`).
- **Auto-scaling Python worker pool** — same model as Robyn's
  `BlockingRunnerPool`. The pool starts with `RIVEX_WORKERS` fixed
  threads (auto-detected CPUs clamped to [2, 32]); when the queue
  backs up, additional threads are spawned on demand (rate-limited
  to one spawn per 350 µs) and exit after 30s of idle. Disable
  with `RIVEX_AUTO_SCALE=0`.
- **CLI: `rivex run --mode {auto,async,sync,asgi}`** and
  **`--fast`** — the `--fast` flag auto-tunes the worker count to
  `2*CPU+1` (same recipe Robyn uses for `--fast`). Legacy
  `--sync` / `--asgi` flags still work as aliases.
- **uvloop integration** — when `uvloop` is installed, the Python worker
  threads install it via the modern `EventLoopPolicy` API on startup
  (replaces Robyn's deprecated `uvloop.install()` call).
- **`io-uring` feature flag** — opt-in Linux io-uring driver. Build
  Rivex with `maturin develop --features io-uring` to enable.
- **`.cargo/config.toml`** — linker flags for PyO3 extension modules
  on macOS (both Intel and Apple Silicon) and Linux. Same recipe
  Robyn uses.
- **`bench/run_bench.py`** — minimal benchmark harness comparing all
  three engines on four representative workloads (small JSON, larger
  JSON, path parameter, const route).

### Performance
- **Release profile tuned** — workspace `[profile.release]` now sets
  `lto = "fat"`, `codegen-units = 1`, `panic = "abort"`, `strip = "symbols"`,
  and `opt-level = 3` (mirrors the recipe Robyn uses). Plus a
  `[profile.release.build-override]` for build scripts.
- **Const-route cache** in `rivex-routing` (new `ConstRouter` struct) —
  `HashMap<(Method, path), CachedResponse>` lookup before matchit.
  Static endpoints (health checks, OpenAPI docs, landing pages) skip
  the entire dispatch pipeline. Wired into both Rust engines
  (`listener.rs` for async, `sync_server.rs` for sync) and into the
  Python ASGI adapter for the `asgi` mode.
- **Pre-computed handler arity** — at registration, introspect the
  handler's signature once and cache a `arity_0: bool` flag. Per request
  the worker dispatches with `call0()` for 0-arg handlers, skipping the
  `request_to_py_dict` allocation entirely (Robyn's
  `function.number_of_params == 0` trick).
- **`pyclass(freelist = N)`** on hot per-request pyclasses
  (`RivexServer`, `RivexSyncServer`, `RivexASGI`, `SharedState`,
  `RateLimitState`, `StreamSender`, `PyWebSocket`). PyO3 keeps a pool of
  reusable instances so the per-request allocation is a pointer swap.
- **Listen backlog raised 8192 → 16384** to match Robyn and absorb load-
  balancer bursts.
- **TCP keep-alive** on accepted streams was already in place
  (`configure_keepalive` in `listener.rs`).
- **Sync-server hot-path optimisations**:
  - Thread-local scratch buffer instead of `vec![0u8; 65536]` per
    request.
  - Pre-baked status-line bytes for the 15 most common HTTP codes,
    avoiding `format!` on every response.
  - Skip the `to_vec()` copy when the body fits in the read buffer.
  - **HTTP/1.1 keep-alive loop** on the sync server. Each TCP
    connection now serves multiple requests; the per-thread scratch
    buffer is reused across requests on the same connection.
- **Auto-bake trivial handlers** — handlers wrapped with
  `@cached_response()` (or anything that exposes `__call_baked__`)
  are now promoted to a Rust-side const route at server start.
  Subsequent requests bypass Python entirely — same fast path as
  `app.add_const_route`. This is the same trick Robyn's
  `ConstRouter` uses and it's the single biggest win for "hello
  world"-style workloads: async engine goes from ~25k rps to
  ~165k rps on the same hardware (vs uvicorn's ~63k rps).
- **Multi-process async workers** — `app.run_async(workers=N)`
  spawns N processes that each bind the same port via
  `SO_REUSEPORT`. The kernel hashes the source 4-tuple and
  load-balances connections. Each worker has its own GIL, breaking
  the GIL serialisation bottleneck. The first version of this was
  actually slower than single-process for CPU-bound workloads;
  the real fix was the auto-bake optimisation above.

### Benchmarks (wrk -t4 -c128 -d 15s, hello-world route, macOS)

| Engine                          |  RPS    | p99     | vs uvicorn |
|---------------------------------|--------:|--------:|-----------:|
| `async` + auto-bake             | 163,678 | 2.45 ms | **2.59×**   |
| `sync` + auto-bake              | 113,359 | 75 ms   | **1.80×**   |
| `asgi` (uvicorn baseline)       |  63,147 | 2.65 ms | 1.00×       |
| `async` + pure const-route      | 166,167 | 2.54 ms | **2.63×**   |
| `sync`  + pure const-route      | 127,087 | 0.072 ms | **2.01×**  |

The sync engine has lower throughput but **30× lower latency** than
the async engine (72µs vs 2.4 ms at p99) — pick async for raw RPS,
sync for tail-latency-sensitive APIs.

### Fixed
- `RivexResponse` is now `#[derive(Clone)]` so it can live in the
  const-route cache without re-allocating.
- `_run_uvicorn_workers` had a pre-existing `registered_paths.add("/")`
  reference to a variable that didn't exist in the function scope —
  removed the dead statement. The unused `uvicorn` and `sys` imports
  were also dropped.
- `RivexSyncServer` and `RivexServer` (the Python wrappers) are now
  both populated at construction time so `add_const_route` works on
  both engines.
- The `_rivex_invoke_dispatch` Rust helper (used by the optional
  contextvars isolation path) is now correctly registered in the
  Python module so users can opt in via their own middleware.

### Tests
- `tests/test_modes_and_const.py` — 8 new tests covering `run(mode=…)`
  routing, `add_const_route` validation, and live end-to-end checks
  that both engines serve the same route table identically.

## [0.2.0] - 2026-06-16

### Added
- **Plugin architecture** — third-party packages can now register
  themselves through Python entry points under
  ``rivex.plugins.{admin,codegen,scaffold}``.  The base ``Plugin``
  class lives in ``rivex.plugins`` and is re-exported as
  ``rivex.Plugin``.
- **Companion packages** (optional extras) — ``rivex[admin]``,
  ``rivex[codegen]``, ``rivex[scaffold]``, ``rivex[all]`` install the
  admin dashboard, the resource scaffolder, the project scaffolder,
  or all three.  The core wheel stays small and dependency-free apart
  from ``pydantic`` and ``orjson``.
- **Pluggable body coercion** — ``rivex._bodies.SCHEMAS`` lets users
  register a new body backend (``detect`` + ``coerce``) for any
  library that exposes a Pydantic-like model class.  Built-in
  adapters for Pydantic, Schemax, Marshmallow, and plain dicts.
- **Typed path parameters** — patterns like ``/items/{id:int}`` and
  ``/codes/{code:re:[A-Z]{2}-[0-9]+}`` are validated against the
  path parameter's declared type or regular expression.  Falls
  through to the Python path in tests; the Rust path does the
  matching for real.
- **Host-scoped routing** — routes registered with
  ``@app.get("/x", host="api.example.com")`` only match when the
  incoming ``Host`` header matches.  Implemented end-to-end
  (test client honours the header, runtime filters by host).
- **HTTPS redirect middleware** —
  ``app.add_middleware(HTTPSRedirectMiddleware)`` now produces a
  fully-qualified ``https://<host><path>?<query>`` redirect URL
  using the real Rust ``build_redirect_url`` helper.
- **Singleton-scoped dependencies** —
  ``app.get("/x")(Depends(provider, scope="singleton"))`` resolves
  the provider once per process instead of per request.
- **Self-contained wheel** — the compiled ``rivex_core`` extension
  is now bundled inside the ``rivex`` wheel by maturin.  No more
  separate ``rivex-core`` package to install.

### Changed
- **Bumped to 0.2.0** because the plugin entry-point and singleton
  scope additions are additive but observable — a 0.1.x application
  that happened to register a class named ``Plugin`` in
  ``sys.modules`` would now collide with the new built-in.
- **Pytest collection** — the suite now sets
  ``testpaths = ["tests"]`` and skips the ``rivex_scaffold/template``
  and ``mvc`` directories from a root-level conftest.  The template
  project ships its own ``tests/`` folder that would otherwise
  collide on import.
- **TestClient is in-process** — the in-Python dispatch path is
  exercised by default; tests no longer require a running Rust
  server.  Real-binary-only suites (websocket end-to-end, the
  ``test_rust_features`` direct-Rust-api suite, the JWT-signing
  contract tests) are auto-skipped when the stub is active and
  re-enabled by installing the bundled native extension.
- **Stale deprecation shim** — the
  ``from rivex import schemax`` back-compat re-export now emits a
  ``DeprecationWarning`` that points users at the standalone
  ``schemax`` package.

### Fixed
- `_injection.py`: undefined name `_singleton_cache` introduced when
  singleton-scope support was added.
- `rivex/__init__.py`: F401 lint noise on the re-exported
  ``schemax`` and ``_bodies`` symbols.
- `openapi.py`: missing top-level imports + I001 import-sort noise
  after the recent OpenAPI overhaul.
- `tests/test_scaffold.py`: duplicate test definition
  (``test_template_appconfig_exposes_settings``) that broke
  collection under pytest 8.
- `tests/conftest.py`: the Python stub for ``rivex_core`` now
  covers the full surface the test suite probes (JWT, SSE,
  CORS, content negotiation, host filtering, regex path
  matching, multipart, rate-limit, shared state, etag,
  JWT decode/encode with the ``(payload_json, secret,
  expires_in)`` signature the Rust extension uses).
- `tests/test_barebones.py`: autouse fixture now restores the
  original ``rivex`` module after each test so the rest of the
  suite sees a consistent ``Plugin`` class identity.
- 188 ruff errors across the tree, including import sort, unused
  imports, blind exception asserts, and the F811 duplicate
  function definition.

### Production readiness
- **`mypy_path = "stubs"`** in ``pyproject.toml`` plus a
  ``stubs/rivex_core/__init__.pyi`` shim so mypy can resolve the
  ``rivex_core`` top-level module against the bundled
  ``rivex_core.pyi`` stub without the Rust extension being
  built in the dev environment.  Reduces ``mypy`` from 196
  to 0 errors.
- **`src/rivex/_rust.pyi`** stub mirroring the dynamic
  ``_EXPORTS`` surface in ``_rust.py`` so mypy can see the
  validator / hashing functions re-exported by the package.
- **`src/rivex/_bodies.py`** — ``_detect_construct`` no longer
  passes ``type | None`` to ``issubclass``; narrows the
  optional bases into a local first.
- **`src/rivex/_injection.py`** — ``_is_bm`` is now explicitly
  annotated ``Callable[[Any], bool] | None``; ``cached_wrapper``
  uses ``cast(dict, await func())`` to satisfy
  ``no-any-return``.
- **`src/rivex/applications.py`** — assert ``openapi_url`` is
  not ``None`` before registering the OpenAPI route.
- **`src/rivex/gen.py`** — ``gen.pylist`` return type is now
  ``list[Any]`` via a ``TYPE_CHECKING`` alias of the built-in
  ``list`` (the class has a static method named ``list`` that
  shadows the type).
- **`rivex_admin/__init__.py`** — ``_admin_default_db_path``
  fallback now returns ``Path`` (matches the real signature);
  ``from rivex import codegen`` replaced with a real
  ``rivex_codegen`` import wired through ``SimpleNamespace``;
  ``_admin_*`` private attributes annotated with
  ``# type: ignore[attr-defined]``; ``add_route`` calls no
  longer pass coroutines (the ``_codegen_apply`` /
  ``_codegen_cancel`` factory pattern is replaced with a
  single async handler that reads the path param from the
  request). Fixes the
  ``RuntimeWarning: coroutine … was never awaited`` raised
  on every admin test.
- **`rivex_admin/db.py`** — narrow ``cur.lastrowid`` to ``int``
  before passing to ``get_user``; ``list_users`` filters
  ``None`` rows from the ``_row_to_user`` generator.
- **`rivex_admin/cli.py`** — ``main`` uses ``cast(int, …)``
  to satisfy ``no-any-return`` on ``args.func(args)``.
- **`rivex_codegen/_schemas.py`** — ``FieldSpec`` and
  ``ResourceSpec`` are now resolved via a ``TYPE_CHECKING``
  import (the dynamic ``_load_codegen_module()`` is kept for
  the test isolation path).
- **`rivex_codegen/__init__.py`** — assert ``_spec`` and
  ``_spec.loader`` are non-``None`` before calling
  ``module_from_spec`` / ``exec_module``.
- **`rivex_scaffold/__init__.py`** — ``install_deps`` is
  narrowed to ``bool`` after the optional interactive prompt.
- **`rivex_scaffold/template/middlewares/request_id.py`** —
  fixed a copy-paste typo (``from rivex from rivex import
  rivex_core as _rc``) that would have produced invalid code
  in every scaffolded project.
- **`pyproject.toml`** — added ``readme``, ``keywords``,
  ``authors``, full ``[project.urls]`` block, and a richer
  ``classifiers`` list for PyPI publication; added
  ``stubs/`` and ``src/rivex/*.so`` to ``.gitignore`` (via
  ``.gitignore``) and excluded ``rivex_scaffold/template``
  and ``rivex_codegen/templates`` from mypy.
- **New ``LICENSE`` and ``SECURITY.md``** — MIT license text
  and a coordinated-disclosure policy with
   ``sengarsinghshreyansh@gmail.com``.

## [0.1.0] - 2025-05-10

### Added
- Initial release
- `Rivex` application class with FastAPI-compatible decorator API
- `Router` for route grouping with prefix and tag support
- Dependency injection system with `Depends()`, caching, and nesting
- Request/response classes: `JSONResponse`, `HTMLResponse`, `PlainTextResponse`, `RedirectResponse`, `StreamingResponse`
- Middleware system: `CORSMiddleware`, `GZipMiddleware`, `RequestIdMiddleware`, `TrustedHostMiddleware`
- OpenAPI 3.1 schema generation from route signatures and Pydantic models
- Background task execution with `BackgroundTask` and `BackgroundTasks`
- File upload support with `UploadFile`, `File`, and `Form`
- HTTP status code constants via `status` module
- Lifecycle hooks (`startup`/`shutdown`) and custom exception handlers

[0.2.0]: https://github.com/shregar1/rivex-python/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/shregar1/rivex-python/releases/tag/v0.1.0
