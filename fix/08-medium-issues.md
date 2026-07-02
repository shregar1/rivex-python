# Medium Severity Issues

## 8a. CORS Preflight for Host-Constrained Routes

**File:** `src/rivex/applications.py:1179-1186,1260-1267`

OPTIONS preflight handlers for host-constrained routes are registered without the host constraint — they respond to ANY host, creating a potential security bypass.

**Fix:** Carry the `host` constraint through when registering OPTIONS fallback routes.

---

## 8b. In-Flight Tracking Hooks Accumulate on Repeated `run()` Calls

**File:** `src/rivex/applications.py:1123-1124`

`_track_before` and `_track_after` are appended to `_before_request_hooks` and `_after_response_hooks` every time `_drive_rust_server` is called. If `run()` is called multiple times on the same app instance, these lists grow without bound.

**Fix:** Clear and re-add, or guard against duplicates.

---

## 8c. `_build_hook_middleware()` Creates New Class on Every Call

**File:** `src/rivex/applications.py:1658-1691`

Every call to `_drive_rust_server` calls `_build_hook_middleware()`, which defines a new `_HookMiddleware` class. Over repeated `run()` calls, these class objects accumulate in memory.

**Fix:** Define `_HookMiddleware` once at module level.

---

## 8d. `include_router` Raises `AssertionError` Instead of `TypeError`

**File:** `src/rivex/applications.py:447`, `src/rivex/routing.py:437`

`assert isinstance(router, Router)` raises `AssertionError` on misuse. Should raise `TypeError` with a clear message.

**Fix:** Replace `assert` with `if not isinstance(...): raise TypeError(...)`.

---

## 8e. Required Body Validation Skipped (also in HIGH)

**File:** `src/rivex/_injection.py:400-403`

Covered in `04-body-validation.md`.

---

## 8f. Dead Code in `_build_codegen_wrapper`

**File:** `src/rivex/_injection.py:603-626`

`_CompiledGen = None` at line 603 is never reassigned, but the guard at line 619 checks `if _CompiledGen is not None`. This branch is dead code.

**Fix:** Remove the guard or wire up the actual compiled gen import.

---

## 8g. `_CODEGEN_SOURCES` Tuple Re-Created on Every Call

**File:** `src/rivex/_injection.py:726-727`

`_CODEGEN_SOURCES` is defined inside `build_handler_wrapper`, re-creating the tuple on every call. Should be a module-level constant.

---

## 8h. `_run_with_reload` Subprocess Uses Legacy `app.run()` Without Explicit Mode

**File:** `src/rivex/cli.py:373-374`

The reload subprocess calls `app.run()` without specifying `mode=`, defaulting to the native Rust engine, but the reload loop manages restarts manually via subprocess (not uvicorn's watchfiles). The native engine and manual subprocess restarts may conflict.

---

## 8i. `os.execvp` in Uvicorn Adapter Bypasses Cleanup

**File:** `src/rivex/contrib/uvicorn.py:150`

When `workers > 1`, `os.execvp` replaces the current process. The `return` on line 151 is unreachable. All cleanup (shutdown hooks, lifespan exit, DB disconnect) in the parent is bypassed.

---

## 8j. Duplicate `_apply_middleware` in `asgi.py` and `applications.py`

**File:** `src/rivex/asgi.py:139-162`, `src/rivex/applications.py:1693-1716`

Identical `_apply_middleware` method duplicated across two files. Maintenance risk.

**Fix:** Factor into a shared utility module.

---

## 8k. Singleton Dependency Cache Has No Locking

**File:** `src/rivex/_injection.py:43`

`_SINGLETON_CACHE` is a module-level dict accessed without synchronization. Under concurrent load, two requests could both create a singleton instance, with one overwriting the other, breaking the singleton guarantee.

**Fix:** Use `threading.Lock` or a concurrent data structure.

---

## 8l. Optional Complex Types Silently Fail Coercion

**File:** `src/rivex/_injection.py:1282-1322`

For `Optional[List[str]]` query parameters, the type hint is peeled to `list[str]`, which is not matched by the hard-coded dispatch (only handles `int`, `float`, `bool`). The raw string is returned instead of a parsed list.

**Fix:** Add recursive type coercion for generic types.
