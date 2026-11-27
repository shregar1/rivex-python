# Rust Migration Analysis: Python -> Rust Core

## Scope

Analyze every Python module in the Rivex Python SDK and classify what can be moved to the existing Rust core extension (`rivex_core`, a PyO3 extension at `../core.rivex.vexarr.com/crates/rivex-python/`).

---

## Already in Rust

These Python functions/classes already delegate to the native extension (but may have Python fallbacks):

### Core compat (`core/_compat.py`)
- `get_header()` -> `_rc.headers_get()`
- `json_error_response()` -> `_rc.json_serialize()`
- `parse_cookies()` -> `_rc.parse_cookies()`
- `client_ip()` -> `_rc.extract_client_ip()`

### Crypto (`auth/crypto.py`) — **entirely Rust**
- `sha256/sha512`, `aes_gcm_encrypt/decrypt`, `pbkdf2_derive/verify`, `random_bytes/token/hex`, `ed25519_keygen/sign/verify`

### JWT (`auth/jwt.py`)
- `encode()`, `decode()`, and jwt_required's `_verify()` -> Rust when `HAS_CORE`

### Validators (`_rust.py`)
- `hash_password`, `verify_password`, `hash_bcrypt`, `hash_argon2`
- `validate_email`, `validate_url`, `validate_ip`, `validate_uuid`, `validate_phone`
- `validate_json_schema`, `is_ascii`, `validate_iban`, `format_iban`, `luhn_check`
- `sanitize_html`, `strip_html_tags`

### Serialization
- `_json.py`: `dumps`/`loads` -> `rivex_core.json_serialize`/`json_deserialize`
- `gen.py` (JSON generator): Entirely Rust via `CompiledGen`, `GenField`, `gen_list_json`
- `serialization.py`: Default serializer is `rivex_core.json_serialize`

### Responses (`core/responses.py`)
- `Response.set_cookie()` -> `_rc.build_set_cookie()`
- `EventSourceResponse.format_event()` -> `_rc.format_sse_event()`

### Requests (`core/requests.py`)
- `body_json()` -> `_rc.json_deserialize()`
- `form()` / `query_params` -> `_rc.parse_query_string()`

### Params (`core/params.py`)
- `_ParamBase.validate()` -> `_rc.validate_number()` / `_rc.validate_string()`

### WebSocket (`protocols/websocket.py`)
- Frame encoding (send_text, send_bytes, close) -> Rust
- `is_websocket_upgrade()` -> `_rc.is_websocket_upgrade()`

### Middleware (`middleware/middleware.py`)
- `CORSMiddleware` -> `_rc.build_cors_headers()`
- `RequestIdMiddleware` -> `_rc.generate_request_id()`
- `GZipMiddleware` -> `_rc.gzip_compress()`
- `TrustedHostMiddleware` -> `_rc.check_trusted_host()`
- `HTTPSRedirectMiddleware` -> `_rc.build_redirect_url()`
- `CompressionMiddleware` -> `_rc.gzip_compress()`

### Caching (`data/caching.py`)
- `_md5_etag()` -> `_rc.md5_hex()`
- `_etag_match()` -> `_rc.etag_matches()`

### OpenAPI (`openapi/openapi.py`)
- `build_docs_html()`, `build_redoc_html()`, `build_health_html()` -> Rust renderers

### Datastructures (`datastructures.py`)
- `Headers.get()` -> `_rc.headers_get()`
- `Headers.getlist()` -> `_rc.headers_get_all()`

### Native handlers (`native/`)
- `health.py`, `redirects.py`, `openapi_spec.py`, `static_files.py` -> all Rust-backed

### Application (`core/applications.py`)
- `add_const_route()` -> Rust server
- Server objects (`RivexServer`, `RivexSyncServer`) -> Rust PyO3 classes

---

## Top Priority Rust Candidates

### 1. Response normalizer (`core/_injection.py:972-1099`)
- `_normalize_response_fast()`: 15+ isinstance checks, tuple unpacking, dict construction on every response
- **Approach**: Rust function via PyO3 that accepts any Python object, pattern-matches types, and builds the response dict
- **Speedup**: ~2-5x for normalization path

### 2. Codegen handler wrapper (`core/_injection.py:84-275, 610-962`)
- `build_handler_wrapper()` + `_build_codegen_wrapper()`: Uses `exec()` to compile Python source at runtime for parameter extraction
- **Approach**: Rust `HandlerWrapper` PyO3 class that stores pre-parsed param metadata and extracts params natively
- **Speedup**: ~3-10x for parameter extraction on complex handlers

### 3. Body coercion (`core/_bodies.py:569-804`)
- `coerce_body()`, `coerce_form_data()`, `_BODY_COERCERS` dispatch: Per-request type coercion and body parsing
- **Approach**: Rust-native type coercers for int/float/bool/str, faster JSON deserialization, cached type detection
- **Speedup**: ~3-5x for body parsing

### 4. Headers data structure (`datastructures.py`)
- `Headers` class: O(n) linear scan for header lookups
- **Approach**: Rust `HeadersMap` backed by case-insensitive `HashMap`/`IndexMap`, exposed as PyO3 class
- **Speedup**: ~10-100x for header lookups (O(n) → O(1))

### 5. JSON encoder (`serialization/encoders.py`)
- `jsonable_encoder()`: Recursive Python object walk with isinstance checks
- **Approach**: Rust recursive walker calling `__dict__`/`model_dump`/dataclass fields via PyO3
- **Speedup**: ~2-5x for complex nested object serialization

### 6. OpenAPI spec generation (`openapi/openapi.py`)
- `generate_openapi()` + `_build_operation()`: Heavy `inspect.signature()` walks and dict construction at startup
- **Approach**: Route metadata already in Rust; generate spec natively without Python introspection
- **Speedup**: ~2-4x startup time (not per-request)

### 7. Middleware chain (`middleware/middleware.py`)
- Port these to fully Rust-native (primitives already exist):
  - `MaxBodySizeMiddleware` (trivial)
  - `CORSMiddleware` (already has `build_cors_headers`)
  - `SecurityHeadersMiddleware` (static header list)
  - `MethodOverrideMiddleware` (simple header read)
  - `HTTPSRedirectMiddleware` (already has `build_redirect_url`)
  - `TrustedHostMiddleware` (already has `check_trusted_host`)
- **Speedup**: Eliminates Python-GIL boundary for these middleware

### 8. Route registration loop (`core/applications.py:1214-1482`)
- `_drive_rust_server()`: Iterates all routes, builds wrappers, registers on Rust server
- **Approach**: Rust-native registration accepting `RouteRecord`-like objects; build middleware chain on Rust side
- **Speedup**: Faster startup, elimination of Python wrapper objects

---

## Secondary Candidates

### Validation (`core/params.py:66-109`)
- `_ParamBase.validate()` Python fallback has manual gt/ge/lt/le and regex matching — all can be pure Rust

### File response (`core/responses.py:298-335`)
- `FileResponse`: `os.stat()`, `mimetypes`, file I/O — Python wrapper overhead; Rust could do zero-copy

### Pagination (`data/pagination.py`)
- `Page.dict()`, `CursorPage.dict()`, `paginate()`: Serialization and slicing — simple CPU-bound logic

### WebSocket frame parsing (`protocols/websocket.py:211-273`)
- `_read_frame_py()`, `_write_frame()`: struct pack/unpack, bit manipulation, masking — Rust would be faster

### Rate limiting middleware (`middleware/middleware.py:271-328`)
- Token-bucket algorithm with dict state — Rust `RateLimitState` already exists

### IP filtering middleware (`middleware/middleware.py:443-476`)
- CIDR matching via `ipaddress` module — CPU-bound loop

### Application helpers (`core/applications.py`)
- `url_for()` (O(n) scan), `mount()`, `include_router()`, `include_controller()`: Dict/list manipulation at startup

### Serializer validation (`serialization/serializers.py`)
- `Serializer.to_internal_value()`, `is_valid()`: Field iteration, type coercion, validator chaining

### OpenAPI helper functions (`openapi/openapi.py`)
- `_type_to_schema()`, `_model_to_ref()`, param detection helpers: Type introspection and dict construction

### MIME type utilities
- `FileResponse` mimetype detection, static file serving — can use Rust `mime_guess` crate

---

## Not Suitable for Rust

| Reason | Examples |
|--------|----------|
| Async generators / streaming | `StreamingResponse`, `EventSourceResponse` |
| Decorator registration | `route()`, `@app.get()`, `@app.post()` |
| Config/setup code | `Rivex.__init__()`, `run_async()` |
| Event loop management | `_run_coroutine_sync()` |
| User callable wrappers | `authenticated()`, `admin_only()`, `jwt_required()` |
| Signal dispatch | `Signal.send()` / `send_async()` |
| Third-party library integration | Pydantic, Strawberry, Jinja2, Marshmallow |
| OS/process management | multiprocessing, signal handling |
| ASGI adapter | `__call__()` (ASGI) |
| Plugin system | Plugin loading/registration |

---

## Recommended Phasing

| Phase | Work | Impact |
|-------|------|--------|
| **Phase 1** | Simple middleware: MaxBodySize, SecurityHeaders, MethodOverride | Low effort, immediate payoff |
| **Phase 2** | Rust `HandlerWrapper` replacing `build_handler_wrapper()` + codegen | Highest impact: 3-10x on handler path |
| **Phase 3** | Rust `HeadersMap` replacing Python `Headers` | Eliminates O(n) header scans |
| **Phase 4** | Rust body coercers + `coerce_body()` replacement | 3-5x on body parsing |
| **Phase 5** | Middleware ports: CORS, GZip, TrustedHost, HTTPSRedirect, IPFilter | Eliminates GIL crossing for middleware |
| **Phase 6** | Rust `_normalize_response_fast()` | 2-5x on response path |
| **Phase 7** | Rust `jsonable_encoder()` | 2-5x on complex serialization |
| **Phase 8** | OpenAPI generation in Rust | 2-4x faster startup |
| **Phase 9** | Route registration (`_drive_rust_server()`) in Rust | Eliminates Python wrapper objects |
