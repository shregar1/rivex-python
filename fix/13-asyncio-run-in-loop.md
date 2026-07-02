# Multiple `asyncio.run` / `loop.run_until_complete` calls from inside running event loop

**Severity:** HIGH
**Files:**
- `src/rivex/applications.py:721` (`_run_hooks`)
- `src/rivex/applications.py:739` (`_enter_lifespan`)
- `src/rivex/applications.py:752` (`_exit_lifespan`)
- `src/rivex/testing.py:121` (`TestClient.request`)

## Problem

Multiple places in the SDK use `asyncio.run(coro)` or `loop.run_until_complete(coro)` to drive async coroutines. Both patterns **fail when called from inside an already-running event loop**, which is the default state during normal request handling.

```python
# applications.py:717-723 — _run_hooks
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = None
if loop and loop.is_running():
    loop.run_until_complete(hook())  # ← BUG: cannot call from inside same loop
else:
    asyncio.run(hook())              # ← BUG: cannot call if loop is running
```

```python
# testing.py:121 — TestClient.request
raw = asyncio.run(outer_chain(request_data))  # ← BUG if event loop is running
```

The `if loop and loop.is_running(): loop.run_until_complete(...)` branch is **doubly broken**:
- If a loop IS running, `loop.run_until_complete(coro)` from inside the
  same thread (which is the only thread on the running loop) deadlocks
  or raises `RuntimeError: This event loop is already running`.
- The intent was clearly "drive the coroutine somehow", but the
  implementation just calls a method that won't work.

The `asyncio.run(...)` branch fails with:
- `RuntimeError: asyncio.run() cannot be called from a running event loop`
  (Python 3.10+)
- Or in some edge cases: silently does nothing while the loop keeps running

## Reproduce

```python
import asyncio
from rivex import Rivex

app = Rivex()

@app.on_event("startup")
async def startup_hook():
    print("startup!")

# Synchronous context — works
with app._enter_lifespan():
    app._run_hooks(app._startup_hooks)
# → startup!

# Async context — fails
async def main():
    with app._enter_lifespan():
        # RuntimeError: This event loop is already running.
        app._run_hooks(app._startup_hooks)

asyncio.run(main())
```

For `TestClient`:
```python
import asyncio
from rivex.testing import TestClient
from your_app import app

async def main():
    # TestClient.request() calls asyncio.run() at line 121
    client = TestClient(app)
    resp = client.get("/")  # ← RuntimeError: This event loop is already running.

asyncio.run(main())
```

## Impact

- **Lifespan hooks fail in async contexts** — the most common case
  during test setup that uses `asyncio.run` or async fixtures.
  Any startup hook that does network I/O (DB connect, HTTP probe)
  will silently skip in async contexts.
- **TestClient is unusable in async test fixtures** — only works in
  pure-sync contexts. Since pytest-asyncio's `event_loop` fixture
  provides an async context, `TestClient` cannot be used in
  `async def test_*` functions without working around this.
- **TestClient also fails inside Jupyter notebooks** (which run an
  event loop), making interactive testing painful.
- **Hidden behavior** — when the code is reached during a running
  loop, the call appears to succeed (returns silently) but the
  coroutine never actually executes, so hooks like DB init never run
  and the next request fails with "no database" errors.

## Fix

The correct fix is to never call `asyncio.run` or `loop.run_until_complete`
from inside a request handler. Instead:

```python
def _run_hooks(self, hooks: list[Callable]) -> None:
    for hook in hooks:
        if asyncio.iscoroutinefunction(hook):
            # Find a loop to use
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop and not loop.is_running():
                # No running loop — safe to use asyncio.run
                asyncio.run(hook())
            elif loop and loop.is_running():
                # We're inside the running loop. Schedule the task
                # and block until it completes.
                future = asyncio.run_coroutine_threadsafe(
                    hook(), loop
                )
                future.result()  # blocks until done
            else:
                # No loop exists — create one
                asyncio.run(hook())
        else:
            hook()
```

The real architectural fix: the SDK should **always run inside an
async context** (its main entry point is `app.run_async()` which starts
its own loop). The sync API is just a thin wrapper for convenience.
The current implementation is incomplete and dangerous.

## Workaround

Until fixed, projects that need to call `_run_hooks`, lifespan
methods, or `TestClient.request` from inside a running loop should:

1. Use `pytest.mark.asyncio` with `loop_scope="session"` carefully
2. Or wrap calls in `asyncio.get_event_loop().run_until_complete(...)`
   from a separate thread
3. Or, simplest: avoid calling these methods from inside a running
   loop — call them BEFORE the loop starts (e.g. in a sync test
   setup) or AFTER it stops (in a finalizer)
