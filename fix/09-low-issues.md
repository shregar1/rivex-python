# Low Severity Issues

## 9a. Inconsistent Short-Circuit Behavior in Lifecycle Hooks

**Files:** `src/rivex/applications.py:1667`, `src/rivex/routing.py:217`

App-level `_HookMiddleware.process` short-circuits when `result` is any `dict`. Router-level `_LifecycleHookMiddleware.process` only short-circuits when `result` is a `dict` AND has a `"status"` key. This means `before_request` hooks behave differently depending on where they're registered.

---

## 9b. `_run_hooks` Creates New Event Loop Per Async Hook

**File:** `src/rivex/applications.py:1718-1730`

Each async startup hook without a running loop gets its own `asyncio.run(hook())`, creating a new event loop per hook. Hooks cannot share event-loop-scoped state.

---

## 9c. `_enter_lifespan()` No Guard Against Re-Entrance

**File:** `src/rivex/applications.py:1744-1763`

Calls `self._run_async(self._db.connect_all())` whenever `self._db._configs` is non-empty, without checking if pools are already connected. Double-entering lifespan would try to connect again.

---

## 9d. `RouteGroup._route` Mutates `kwargs` Destructively

**File:** `src/rivex/routing.py:252-267`

Pops `"tags"` and `"middleware"` from `**kwargs` before passing the rest to `RouteRecord`. If `RouteRecord` ever adds these as constructor params with different semantics, the mutation would prevent forwarding.

---

## 9e. Controller `is_controller()` Doesn't Check Abstract Classes

**File:** `src/rivex/routing.py:154-157`

Returns `True` for any `Controller` subclass, even abstract ones. `controller_to_router()` then instantiates without checking if the constructor requires arguments.

---

## 9f. CLI `-k` Detection Too Broad

**File:** `src/rivex/cli.py:449`

`"-k" in a` matches any arg containing `-k` (e.g., `--key=value`). Should be `a == "-k"` or `a.startswith("-k")`.

---

## 9g. `_import_app` Permanently Modifies `sys.path`

**File:** `src/rivex/cli.py:277`

`sys.path.insert(0, ".")` is never cleaned up. If called multiple times, `"."` is inserted repeatedly.

---

## 9h. `createsuperuser` Loses `--help` Support

**File:** `src/rivex/cli.py:103`

Subparser has `add_help=False` but no custom help handling, so `rivex createsuperuser --help` prints nothing useful.

---

## 9i. `asgi_app = None` Module-Level Footgun

**File:** `src/rivex/contrib/uvicorn.py:181`

`asgi_app = None` at module level means `from rivex.contrib.uvicorn import asgi_app` gives `None`. Users must call `make_asgi_app(app)` first.

---

## 9j. `make_asgi_app` is No-Op Identity Function

**File:** `src/rivex/contrib/uvicorn.py:160-177`

Returns `app` unchanged despite documentation suggesting it "wraps" the app.

---

## 9k. Redundant `X as X` Import Aliases

**File:** `src/rivex/__init__.py:84-110`

8 instances of `from rivex.forms import BooleanField as BooleanField` — a no-op boilerplate pattern.

---

## 9l. Duplicate Entries in `__all__`

**File:** `src/rivex/__init__.py`

`BackgroundTask`, `BackgroundTasks`, `CacheMiddleware`, `ETagMiddleware`, `cached_response` appear twice in `__all__`.

---

## 9m. `schemax` Eager Import Triggers Deprecation Warning

**File:** `src/rivex/__init__.py:1`, `schemax/__init__.py`

Every `import rivex` triggers a `DeprecationWarning` from the schemax compat shim, even for users not using schemax.

---

## 9n. Redundant `uvicorn` Optional Dependency

**File:** `pyproject.toml:46,120`

`uvicorn>=0.30` is a core dependency AND an optional dependency under `[project.optional-dependencies] uvicorn`. The extra is meaningless since uvicorn is always installed.

---

## 9o. Plugin Loader Silently Swallows All Errors

**File:** `src/rivex/plugins.py:116-123`

`except Exception` catches `SystemExit`, `KeyboardInterrupt`, `ImportError`, `SyntaxError` and only logs a warning. A plugin with a syntax error is silently skipped.

---

## 9p. Signal.send() Doesn't Handle Async Receivers

**File:** `src/rivex/events.py:23-31`

`Signal.send()` calls receivers synchronously. If a receiver is a coroutine function, it returns an unawaited coroutine object. No warning or documentation about this.
