# Multi-Worker Uvicorn Mode is Broken

**Severity:** HIGH
**File:** `src/rivex/contrib/uvicorn.py:127,143-144`

## Problem

When `workers > 1`, the code resolves the app module name via:

```python
module_name = getattr(app, "__module__", None)
```

This returns `"rivex.applications"` (the module where `Rivex` is defined), NOT the user's module. The constructed uvicorn command becomes:

```
uvicorn rivex.applications:asgi_app
```

which does not point to the user's app, starting a completely wrong server.

## Impact

- `rivex run myapp:app --workers 4` launches a non-functional server
- Multi-process mode is entirely broken

## Fix

Pass the original module path through from the CLI or store the import path on the app instance during `_import_app()`.
