# Required Body Parameter Validation Silently Skipped

**Severity:** HIGH
**File:** `src/rivex/_injection.py:400-403`

## Problem

When `ctx.body` is empty/falsy (no request body sent), the code returns the parameter's default value regardless of whether it's `required=True`:

```python
if not ctx.body:
    if not default.required:
        return default.default
    return default.default  # ← required? still returns default!
```

## Impact

- A required body parameter with no default silently gets the default value instead of raising a 422 validation error
- API endpoints accept invalid requests that should be rejected

## Fix

```python
if not ctx.body:
    if default.required:
        raise HTTPException(422, "request body is required")
    return default.default
```
