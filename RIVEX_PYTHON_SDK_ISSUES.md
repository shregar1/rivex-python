# Rivex (Python SDK) — issues & suggested fixes

Findings from building a full production API on Rivex + ORMX
(~220 routes, 830 tests). Each item is grounded in
the current source under `rivex-python/src/rivex/` with a concrete
fix. Ordered by severity.

Paths below are relative to `rivex-python/src/rivex/`.

**Status:** #1, #2, and #3 are **fixed in this change** (patches + regression
tests applied to the source below). #4 is effectively resolved by #1's fix.
Test runs after the changes: `test_injection.py` 26, `test_routing.py` 12,
`test_pluggable_validation.py` (+routing) 44, injection backends 71,
`test_testing.py` + `test_testing_extras.py` 17 — all passing.

---

## 1. BUG (high) — bad `int`/`float`/`bool` path & query params return 500, not 422  ✅ FIXED HERE

**Where:** `_injection.py` — `_extract_path` (~L275), `_extract_path_param` (~L288),
`_extract_query` (~L308). Coercion helper `_coerce` (~L1301).

**What happens:** a typed primitive param that can't be coerced raises a bare
`ValueError` that nothing catches, so it surfaces as an unhandled **500**:

```
GET /stores/abc/products      →  500   (store_id: int, "abc" not an int)
GET /stores/99999999999999999999/...  →  500   (overflows the Rust i64 coercer)
GET /x?days=abc               →  500   (days: int query param)
```

`_coerce` delegates to the Rust core (`_rc.coerce_value(value, "int")`) or
plain `int(value)`; on failure that's a raw `ValueError`
(`"Cannot convert 'abc' to int"`), and the three extractors above call `_coerce`
**without a try/except**:

```python
# _extract_path — no guard around _coerce
raw = ctx.path_params.get(name)
if raw is not None:
    return _coerce(raw, hint)          # ← ValueError escapes → 500
```

**The inconsistency that proves it's a bug:** the sibling extractor for
`Query(...)`-declared params, `_extract_query_param` (~L323), *does* guard it and
returns a proper 422:

```python
try:
    val = _coerce(values[0], hint)
except (ValueError, TypeError) as e:
    raise RequestValidationError(
        [{"loc": ("query", name), "msg": str(e), "type": "type_error"}]
    ) from e
```

So `?limit=abc` on a `Query(...)` param → 422, but a plain `limit: int` query
param, **and every typed path param**, → 500. The float branch is half-guarded
too: `_coerce` raises `HTTPException(422)` for non-finite floats (`inf`/`nan`)
but a non-numeric float still raises an uncaught `ValueError`.

**Impact:** every route with a typed path param (i.e. almost all of them) 500s on
a non-numeric or out-of-range segment — trivially reachable by any client, and it
pollutes error dashboards / masks real 500s. In our app we had to add a global
`ValueError` exception handler that maps `"Cannot convert … to int"` → 404 and
delegates `ValidationError` → 422, as a workaround.

**Fix:** make the three extractors guard `_coerce` exactly like
`_extract_query_param` already does. E.g.:

```python
def _extract_path(ctx, name, hint, default):
    from rivex.exceptions import RequestValidationError
    raw = ctx.path_params.get(name)
    if raw is not None:
        try:
            return _coerce(raw, hint)
        except (ValueError, TypeError) as e:
            raise RequestValidationError(
                [{"loc": ("path", name), "msg": str(e), "type": "type_error"}]
            ) from e
    ...
```

(Apply the same to `_extract_path_param` around its `_coerce` call, and to
`_extract_query`.) Better still, push the try/except *into* `_coerce` so every
caller is covered by construction and the behaviour can't drift again.

**Applied fix (this change):** the guard was pushed into `_coerce` itself (both
the `RC_V2` core path and the pure-Python fallback), raising
`HTTPException(422)` on a parse/overflow failure — consistent with the
non-finite-float guard already there, and covering all four extractors at once.
Regression tests added to `tests/test_injection.py`
(`test_coerce_bad_int_raises_422_not_valueerror`, `test_coerce_bad_float_raises_422`).
Verified end-to-end: `GET /items/abc` and an i64-overflow segment now return
**422** (were 500); `GET /items/5` still 200.

**Design note:** a malformed path segment is arguably a 404 (the URL names no
real resource) rather than a 422. Whichever you choose, pick one and apply it
uniformly — today the same bad-input class yields 422, 500, or (with our
workaround) 404 depending on how the param was declared.

---

## 2. Missing (medium) — `TestClient` can't control redirect following  ✅ FIXED HERE

**Where:** `testing.py` — `TestClient.request` (~L65), `.get`/`.post` (~L47/50).

**What happens:** `request()` accepts only
`headers, params, json, data, content`. There's no `follow_redirects` (nor
`cookies`/`auth`). Testing any endpoint that returns a 3xx (e.g. an OAuth
callback, or an email click-tracking redirect like ours) is awkward — you can't
say "don't follow, let me assert the `Location`", and there's no documented
default for whether redirects are followed.

httpx and Starlette's `TestClient` both take `follow_redirects=`; Rivex's should
match for parity, since it's otherwise API-compatible enough that people reach
for it the same way.

**Fix:** add `follow_redirects: bool = True` (or `False` to match httpx's newer
default — just document it) to `request()` and thread it through; when `False`,
return the 3xx response as-is instead of dispatching to the `Location`.

**Applied fix (this change):** added `follow_redirects: bool = False`
(+ `max_redirects: int = 20`) to `TestClient.request`. Default `False`
preserves the prior behaviour (the 3xx is returned as-is). When `True`, it
follows `Location` up to `max_redirects`; 303 — and 301/302 from a non-GET/HEAD —
degrade to GET with no body, while 307/308 replay the method and body (standard
semantics). Regression tests added to `tests/test_testing.py`
(`test_test_client_redirects_not_followed_by_default`,
`test_test_client_follow_redirects`).

---

## 3. Footgun (medium) — verb-named route decorators collide with Controller methods  ✅ FIXED HERE

**Where:** `routing.py` — module-level `get`/`post`/`patch`/`delete` (~L121+),
used as `from rivex import get, post` + `@get("...")` on `Controller` methods.

**What happens:** because the decorators share names with HTTP verbs, naming a
`Controller` method after a verb silently shadows the decorator for **every later
method in the same class body** (normal Python class-scope name binding):

```python
from rivex import get, post

class ProductController(Controller):
    @get("")                     # ok
    async def get(self, ...): ...        # ← rebinds the name `get` in class scope

    @get("/{id}")                # TypeError: 'coroutine'/method is not callable
    async def get_one(self, ...): ...
```

The failure is a confusing `TypeError` at class-definition time, far from the
real cause. We hit this and had to rename handlers to `get_x`/`list`/etc.

**Why there's no clean in-code fix:** the failure is a `TypeError` raised
*while the class body is still executing* (the second `@get(...)` calls the
now-shadowed method). That's before `Controller.__init_subclass__` /
metaclass hooks run, so the framework can't intercept it to emit a nicer error.
Left as a documentation + API-shape recommendation rather than a fragile patch:

- Document loudly (a "don't name handlers after verbs" note) — cheap, effective.
- Ship a namespaced decorator so the common import isn't a bare `get` —
  e.g. `from rivex import route` + `@route.get("...")`, which a verb-named
  method can't shadow. This is the recommended real fix; it's an additive API
  change worth a maintainer decision.

**Applied fix (this change):** the verb decorators are now also attached to the
existing `route` function as attributes (`route.get`, `route.post`, `route.put`,
`route.delete`, `route.patch`, `route.head`, `route.options`) in `routing.py`.
`from rivex import route` + `@route.get("...")` is collision-proof (a method
named `get` can't shadow `route`), and both the bare `@get(...)` and
`@route("GET", ...)` forms keep working unchanged. Regression tests in
`tests/test_routing.py` (`test_route_namespace_attributes_match_bare_decorators`,
`test_controller_verb_named_handlers_via_route_namespace` — the latter defines a
Controller with a `get` handler *and* a second `@route.get`, which raises
`TypeError` with the bare import). The docs footgun note is still worth adding so
people reach for `route.get` in Controllers.

---

## 4. Minor — primitive coercion in `_coerce` is duplicated across an RC_V2 / pure-Python fork  ✅ ADDRESSED BY #1

**Where:** `_injection.py` — `_coerce` (~L1301) has two parallel branches
(`if RC_V2:` Rust path vs. pure-Python `int()/float()/bool`). The non-finite
guard exists in both, but the *error-wrapping* (see #1) exists in neither — so
fixing #1 inside `_coerce` also removes the risk of the two branches diverging
again. Worth consolidating the "parse + validate + wrap" logic in one place.

---

## Suggested test additions (would have caught #1 and #2)

- Parametrised: for every primitive param kind (`int`/`float`/`bool`) × every
  source (plain path, `Path(...)`, plain query, `Query(...)`), assert a bad value
  yields 422 (or a deliberate 404 for path) — **never 500**. Today only the
  `Query(...)` cell passes.
- An overflow case (`int` param far outside i64) — same expectation.
- A `TestClient` redirect test asserting both follow and no-follow behaviour.

---

## Related: ORMX (data layer SDK) — separate repo

These aren't Rivex, but they shape every Rivex+ORMX app. **Now written up (and
two fixed) in `oss/ormx/ORMX_PYTHON_SDK_ISSUES.md`.** Summary:

- `NUMERIC`/`DecimalField` columns decode as `None` from the Rust driver → money
  must be stored as `VARCHAR`. (Biggest one — needs the Rust core; documented.)
- **[FIXED]** Integer PKs rendered as plain `INTEGER PRIMARY KEY`, not
  `GENERATED BY DEFAULT AS IDENTITY` → deferred-PK inserts violated NOT NULL.
  Fixed in `ormx/migrations/types.py`.
- **[FIXED]** Connection pool size wasn't exposed through `ormx.connect(...)`
  (backend default 20, not ~10 as first guessed) — a real **production
  concurrency ceiling** and the cause of `asyncio.gather`-heavy tests
  intermittently exhausting the pool. Added `pool_size=` to `connect()`.
- Inherited `BaseModel` fields lose `DbMetadata` (PK/DEFAULT) in `diff_schema`,
  plus a spurious `basemodels` table gets registered. (Documented.)
- A UUID-shaped string bind value is coerced to a `uuid` param, breaking
  `VARCHAR = $1` lookups; needs `$1::text`. (Rust core; documented.)
- `makemigrations` doesn't introspect indexes — hand-added unique indexes are
  invisible (no false drift, but composite-unique can't live on the model).

---

*Generated while building a production API. Line numbers are
approximate — grep the referenced symbol names, which are stable.*
