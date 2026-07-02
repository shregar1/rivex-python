# ASGI Lifespan Protocol Violation

**Severity:** HIGH
**Files:** `src/rivex/asgi.py:413-430`, `src/rivex/applications.py:1744-1763`

## Problem

The ASGI lifespan handler does not send `lifespan.startup.failed` or `lifespan.shutdown.failed` messages when startup/shutdown hooks raise exceptions. The ASGI 3.0 spec requires these failure messages; without them, some ASGI servers may hang indefinitely waiting for the lifespan response.

Additionally, `_enter_lifespan()` has no try/except around `_run_hooks(self._app._startup_hooks)`, so a startup exception crashes the handler inline.

## Impact

- `uvicorn run myapp:app` or any ASGI server may hang on startup/shutdown failure
- The "lifespan protocol appears unsupported" warning from uvicorn is partly caused by this

## Fix

Wrap the lifespan handler's startup/shutdown sections in try/except and emit the proper `*.failed` event:

```python
# In asgi.py lifespan handler:
async def lifespan(self, scope, receive, send):
    # ...
    try:
        await self._enter_lifespan()
        await self._run_hooks(self._app._startup_hooks)
        await send({"type": "lifespan.startup.complete"})
    except Exception:
        await send({"type": "lifespan.startup.failed"})
        return
    # ...
```
