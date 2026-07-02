# SSE Handler Does Not Await Async Generators

**Severity:** HIGH
**File:** `src/rivex/applications.py:356-361`

## Problem

The `sse_handler` does:

```python
raw = func(**path_params)
```

If `func` is an `async def` (even an async generator), calling it returns a coroutine or async generator object — it is never awaited. The result passed to `EventSourceResponse` is a coroutine object, not a useful SSE stream.

For the no-Rust-core fallback path, the entire stream is buffered into memory (blocking call in `_render_body`).

## Impact

- Async SSE handler functions silently return garbage (coroutine objects rendered as text)
- Without the Rust core, SSE is fully buffered in memory (defeats streaming purpose)

## Fix

Check if the result is awaitable and await it:

```python
raw = func(**path_params)
if inspect.isawaitable(raw):
    raw = await raw
```
