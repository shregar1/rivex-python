# `StreamingResponse._render_body()` is broken in async contexts

**Severity:** MEDIUM
**File:** `src/rivex/responses.py` (line 192-211)
**Affects:** streaming endpoints when `HAS_CORE` is False (no Rust
core loaded)

## Problem

`StreamingResponse._render_body()` is the fallback path for when the
Rust core (`HAS_CORE = False`) is unavailable. It tries to collect the
async stream into bytes so the response can be sent synchronously.

The current implementation has a control-flow bug:

```python
def _render_body(self) -> bytes:
    chunks: list[bytes] = []
    if hasattr(self._stream, "__aiter__"):
        async def _collect() -> list[bytes]:
            # ...

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            chunks = loop.run_until_complete(_collect())   # ← BUG
        else:
            chunks = asyncio.run(_collect())              # ← BUG
```

The two branches both fail in real use:

1. **`loop.run_until_complete(_collect())` from inside the running
   loop** — this raises `RuntimeError: This event loop is already
   running.` Because `_collect()` is a coroutine on the same loop,
   you cannot drive it from within the loop. The Python docs say
   `run_until_complete` blocks the calling thread until the future
   completes; if the calling thread is the same thread that is
   already running the loop, this deadlocks.

2. **`asyncio.run(_collect())` from inside the running loop** — also
   raises `RuntimeError: asyncio.run() cannot be called from a running
   event loop` (Python 3.10+). Or, on older Python, it raises
   `RuntimeError: Event loop is closed` after the second call.

The fallback therefore only works in one case: there is NO running
event loop (e.g. when called from a sync context outside a request
handler). In every async context — which is the only context in which
a streaming response is rendered — it fails.

### Reproduce

```python
import asyncio
from rivex.responses import StreamingResponse

async def gen():
    yield b"chunk1\n"
    yield b"chunk2\n"

async def main():
    response = StreamingResponse(gen())
    # In a real request handler, _render_body is called to compute body
    # when HAS_CORE is False. The check below simulates that path:
    body = response._render_body()
    print(body)

asyncio.run(main())
# → RuntimeError: This event loop is already running.
```

## Impact

- Streaming endpoints work fine when `HAS_CORE = True` (the Rust core
  handles streaming natively via `_stream_id`).
- But if the Rust core is not available (some platforms, some test
  environments, some builds), every streaming response is broken.
- The fallback path is also used by `_to_raw()` in the no-core branch.

## Fix

The fix is to use `asyncio.run_coroutine_threadsafe` when called
from a running loop on a different thread, or simply use
`asyncio.get_event_loop().create_task()` and await it when on the same
thread. The simplest correct implementation:

```python
def _render_body(self) -> bytes:
    chunks: list[bytes] = []
    if hasattr(self._stream, "__aiter__"):
        async def _collect() -> list[bytes]:
            result: list[bytes] = []
            async for chunk in self._stream:
                if isinstance(chunk, str):
                    result.append(chunk.encode("utf-8"))
                else:
                    result.append(chunk)
            return result

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            # No running loop — safe to use asyncio.run
            chunks = asyncio.run(_collect())
        else:
            # We're in a running loop. The only way to drive the
            # coroutine is to await it. Since _render_body is sync,
            # we have to use a thread to drive it.
            import threading
            result: list[bytes] = []
            error: list[Exception] = []

            def runner():
                try:
                    result.extend(asyncio.run(_collect()))
                except Exception as e:
                    error.append(e)

            t = threading.Thread(target=runner)
            t.start()
            t.join()
            if error:
                raise error[0]
            chunks = result
    else:
        # Sync iterator
        for chunk in self._stream:
            if isinstance(chunk, str):
                chunks.append(chunk.encode("utf-8"))
            else:
                chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))
    return b"".join(chunks)
```

Alternatively, the simpler fix is to make `_render_body` an `async`
function and `await` it everywhere it's called. But that's a wider
API change.

The real fix is to **stop buffering the stream** when the Rust core
isn't available. Instead, write the chunks directly to the response
stream without buffering them. The no-core fallback should expose
streaming as actual streaming, not fake it via buffering.

## Workaround

Until this is fixed, projects that need streaming responses in
async contexts should:
- Ensure `HAS_CORE = True` (install with the Rust core build)
- Or use a different ASGI server (e.g. starlette + uvicorn) for
  streaming endpoints
