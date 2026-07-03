# Multipart `File()` handlers: scalar siblings silently misbound, form-model validation includes file parts

**Severity:** HIGH
**Files:** `src/rivex/_injection.py:325-336` (`_extract_query`), `src/rivex/_injection.py:690-733` (parameter classification), `src/rivex/_injection.py:543-576` (`_extract_form_model`), `src/rivex/requests.py:127-132` (`Request.form()`)

Found while auditing a production endpoint (`POST /pipeline`) that mixes a
`file: UploadFile = File()` param with a plain `tier: str = "auto"` sibling —
the sibling never received the value clients sent in the multipart body, with
no error anywhere in the stack.

## Issue 1 — untagged scalar next to `File()` is silently bound to query string only, never the multipart body

**Where:** `build_handler_wrapper`'s parameter classification loop, `_injection.py:690-733`.

Every parameter is classified into a `source` by walking an `if/elif` chain.
Anything that isn't `Depends`/`File`/`Form`/`Path`/`Query`/`Header`/`Cookie`/
`Body`, isn't a path param, isn't `Request`/`BackgroundTasks`/`UploadFile`, and
isn't a body-model/`dict`/`bytes` falls into the final `else`:

```python
else:
    # Untagged scalar parameters default to query string lookup.
    params_info.append(("query", name, hint, param.default))
```

So `tier: str = "auto"` next to `file: UploadFile = File()` is classified with
source `"query"`, and `_extract_query` (`_injection.py:325-336`) only ever
reads `ctx.query_params` — it never looks at `ctx.multipart_fields` at all:

```python
def _extract_query(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    values = ctx.query_params.get(name) if ctx.query_params else None
    if values:
        return _coerce(values[0], hint)
    if default is not inspect.Parameter.empty:
        return default
    raise RequestValidationError(...)
```

The result: a caller who sends `tier` as a genuine multipart body field gets
`200` with `tier` silently reset to its Python default — the value they sent
is parsed by `parse_multipart` (it *is* in `ctx.multipart_fields`) and then
never consulted, because the parameter was routed to the query-string
extractor from the moment the signature was inspected, with no relationship
to whether the same handler also declares a `File()`/`Form()` param.

### Repro

```python
from rivex import Rivex, File, UploadFile, TestClient

app = Rivex()

@app.post("/probe")
async def probe(file: UploadFile = File(), tier: str = "auto"):
    content = await file.read()
    return {"tier": tier, "filename": file.filename, "len": len(content)}

BOUNDARY = "----probe"
def multipart_body():
    parts = [
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="tier"\r\n\r\nbalanced\r\n',
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="doc.txt"\r\n'
        f'Content-Type: text/plain\r\n\r\n',
    ]
    return "".join(parts).encode() + b"hello world" + f"\r\n--{BOUNDARY}--\r\n".encode()

client = TestClient(app)
r = client.post("/probe", content=multipart_body(),
                 headers={"content-type": f"multipart/form-data; boundary={BOUNDARY}"})
print(r.json())
# {'tier': 'auto', 'filename': 'doc.txt', 'len': 11}
# EXPECTED: {'tier': 'balanced', ...} — the body clearly contains tier=balanced.

r2 = client.post("/probe?tier=balanced", content=multipart_body(),
                  headers={"content-type": f"multipart/form-data; boundary={BOUNDARY}"})
print(r2.json())
# {'tier': 'balanced', ...} — works, because "query" source reads query_params fine.
# This is what masked the bug in our app: the frontend happened to send tier as
# a query param, not a body field, so nobody noticed the body-field path was dead.
```

Confirmed reproducible against current `main` (`c6c3101`), no ordering
dependency — happens regardless of which multipart part comes first.

### Impact

Any handler with the common FastAPI-style signature
`(file: UploadFile = File(), extra: SomeScalar = default)` silently ignores
`extra` for every caller that sends it as a form field instead of a query
param. There is no error, no warning, no log line — a 200 with wrong data.
This is worse than a validation failure: a caller has no signal that anything
went wrong.

### Suggested fix

When the handler also has a `file`/`form`/`form_model` source in
`params_info` (i.e. `has_multipart` is true), an untagged scalar sibling
should be classified as `"form"` (or checked against both query and
multipart sources at extraction time) instead of unconditionally `"query"`.
At minimum, this should be documented loudly — right now nothing in `File`'s
or the untagged-scalar path's docstring warns that siblings need `Form()` to
see the multipart body.

## Issue 2 — `_extract_form_model` feeds the whole multipart envelope (including `UploadFile` parts) into DTO validation

**Where:** `_injection.py:543-576`.

```python
def _extract_form_model(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    form_data: dict[str, Any] = {}
    if ctx.multipart_fields:
        for fk, fv in ctx.multipart_fields.items():
            form_data[fk] = fv[0] if len(fv) == 1 else fv
    ...
    if form_data:
        return coerce_form_data(form_data, hint)
```

`ctx.multipart_fields` contains *every* part of the multipart body, including
the parts destined for sibling `File()` params (as `UploadFile` instances,
per `parse_multipart` in `uploads.py`). This function copies all of them,
unfiltered, into `form_data`, then validates the whole thing against `hint`.

`Form`'s own docstring (`uploads.py:75-93`) documents the canonical pattern —
a DTO bound via `Form()` alongside a `File()` sibling — and explicitly claims:

> "file is the binary upload (extra multipart fields the DTO doesn't declare
> are ignored)"

That claim only holds if the DTO's model config uses `extra="ignore"`
(pydantic's default). Any DTO using `extra="forbid"` — a completely
reasonable choice for rejecting unexpected client input everywhere else in an
app — gets a spurious 422 because the `file` part is present in the dict
handed to validation:

### Repro

```python
from rivex import Rivex, File, Form, UploadFile, TestClient, Schema

class TierForm(Schema):
    model_config = {"extra": "forbid"}
    tier: str = "auto"

app = Rivex()

@app.post("/probe2")
async def probe2(file: UploadFile = File(), payload: TierForm = Form()):
    ...

# POST multipart body with tier=balanced + file=doc.txt →
# 422: "1 validation error for TierForm\nfile\n  Extra inputs are not permitted
#       ... input_type=UploadFile"
```

Confirmed against current `main` (`c6c3101`).

### Suggested fix

Filter `ctx.multipart_fields` down to entries whose value isn't an
`UploadFile` (or, more precisely, exclude any field name already claimed by a
sibling `"file"`-source parameter) before building `form_data`:

```python
from rivex.uploads import UploadFile

if ctx.multipart_fields:
    for fk, fv in ctx.multipart_fields.items():
        val = fv[0] if len(fv) == 1 else fv
        if isinstance(val, UploadFile):
            continue
        form_data[fk] = val
```

This makes the docstring's claim ("extra multipart fields ... are ignored")
actually true regardless of the DTO's `extra` config, instead of only when
the DTO happens to use `extra="ignore"`.

## Secondary — `Request.form()` doesn't parse `multipart/form-data` at all

**Where:** `src/rivex/requests.py:127-132`.

```python
def form(self) -> dict[str, str]:
    if RC_V2:
        result = _rc.parse_query_string(self._body.decode("utf-8"))
        return {k: (v if isinstance(v, str) else v[0]) for k, v in result.items()}
    parsed = parse_qs(self._body.decode("utf-8"), keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items()}
```

`form()` unconditionally treats the raw body as
`application/x-www-form-urlencoded`, with no check of `self.content_type`.
Called on a genuine `multipart/form-data` body, it silently returns garbage
(the multipart boundary markers and headers get mangled through
urlencoded-style parsing) instead of raising or returning the actual fields:

```python
@app.post("/probe3")
async def probe3(request: Request):
    return {"form": request.form()}

# multipart body with a "tier" field →
# {'form': {'------probe3\r\nContent-Disposition: form-data; name': '"tier"\r\n\r\nbalanced\r\n------probe3--\r\n'}}
```

### Suggested fix

Branch on `self.content_type` and delegate to `rivex.uploads.parse_multipart`
for multipart bodies:

```python
def form(self) -> dict[str, str]:
    content_type = self.content_type or ""
    if "multipart/form-data" in content_type:
        from rivex.uploads import parse_multipart
        fields = parse_multipart(self._body, content_type)
        return {k: v[0] for k, v in fields.items() if not hasattr(v[0], "filename")}
    if RC_V2:
        result = _rc.parse_query_string(self._body.decode("utf-8"))
        return {k: (v if isinstance(v, str) else v[0]) for k, v in result.items()}
    parsed = parse_qs(self._body.decode("utf-8"), keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items()}
```

## Investigated and ruled out — apparent field-order-dependent 422 was a local build artifact, not a rivex bug

While investigating we initially hit a `422 {"file": "Field required"}` when a
`File()` + `Form()`-bound sibling handler received the `file` multipart part
*before* the form field(s) in the body — using a `rivex_core` extension
hand-installed in a machine's global `site-packages` (macOS, darwin build).
We traced this all the way down before writing it up, and it does **not**
hold up as a real `rivex` issue:

1. `core.rivex.vexarr.com` has exactly **one commit in its entire history**
   (`7a41e5b`, "Initial commit") — the Rust multipart parser
   (`crates/rivex-http/src/multipart.rs`, `MultipartForm::parse`) has never
   changed. Reading it directly: it splits the whole body on the boundary
   marker into a `Vec` up front, with no streaming or early-exit logic — it
   is order-independent by construction.
2. We diffed the exact `rivex` 0.2.2 wheel vendored into the downstream app
   (`_injection.py`, `uploads.py`, `requests.py`) against this repo's commit
   `7119b6c` (the pinned Python commit) — **byte-for-byte identical**. So the
   Python-side extraction logic is provably the same code we already read and
   confirmed order-independent in Issues 1–2 above.
3. We tested the *pure-Python* multipart fallback directly (`HAS_CORE` forced
   `False`, bypassing the Rust core entirely) against the current checkout —
   also order-independent, both orderings return `200` with the correct value.
4. The only place the order-dependent 422 ever appeared was a macOS
   `rivex_core.cpython-313-darwin.so` in one machine's global `site-packages`
   — not the manylinux wheel actually vendored/deployed (which can't even run
   on macOS), and with no corresponding commit in `core.rivex.vexarr.com`
   that could explain different behavior from the single, unchanged Rust
   source.

**Conclusion:** this was a stale or otherwise non-matching local build of
`rivex_core` on one developer machine, unrelated to any commit in this repo
or its `core` sibling — not a `rivex` bug. Leaving this section in as a
paper trail in case anyone else hits the same symptom and wonders whether
it's a framework issue: it isn't, check what `rivex_core` build you actually
have installed (`python -c "import rivex_core; print(rivex_core.__file__)"`)
against the wheel your project is supposed to be pinned to.
