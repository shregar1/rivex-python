# Background Tasks & Concurrency

Two related concerns: running work *after* the response is sent (background tasks), and keeping the Rust worker threads free when you must call blocking or CPU-bound code (`run_in_threadpool`).

## Background tasks

Background tasks run once the response has been returned to the client — perfect for sending email, writing audit logs, or kicking off provisioning without making the caller wait.

Declare a `BackgroundTasks` parameter and add work to it:

```python
import time

from rivex import BackgroundTasks, Rivex

app = Rivex()


def send_welcome_email(email: str) -> None:
    time.sleep(0.05)
    print(f"welcome email → {email}")


def provision_workspace(email: str) -> None:
    print(f"workspace provisioned → {email}")


@app.post("/signup", status_code=202)
async def signup(email: str, tasks: BackgroundTasks):
    tasks.add_task(send_welcome_email, email)
    tasks.add_task(provision_workspace, email)
    return {"status": "accepted", "email": email}
```

The response (`202 Accepted`) goes out immediately; the two tasks run afterwards. `add_task(func, *args, **kwargs)` accepts sync or async functions. An exception in a task is logged, not surfaced to the client.

For a single deferred call without the injected collector, attach a `BackgroundTask` to a response directly:

```python
from rivex import BackgroundTask, JSONResponse


@app.post("/notify")
async def notify(user_id: int):
    task = BackgroundTask(send_push, user_id)
    return JSONResponse({"queued": True}, background=task)
```

## Concurrency: run_in_threadpool

Rivex runs handlers on Rust worker threads. A blocking call (a synchronous DB driver, file I/O, image processing, heavy CPU math) holds its worker and the GIL, throttling throughput. Offload such work with `run_in_threadpool`, which runs the function on a separate thread pool and releases the GIL for other workers.

```python
import math

from rivex import run_in_threadpool


def crunch(n: int) -> float:
    return sum(math.sqrt(i) for i in range(n))


@app.get("/compute/{n}")
async def compute(n: int):
    result = await run_in_threadpool(crunch, n)
    return {"result": result}
```

`run_in_threadpool(func, *args, **kwargs)` awaits the result and re-raises any exception in the caller.

### When to use which

| Situation | Use |
| --- | --- |
| Work the client doesn't need to wait for | `BackgroundTasks` |
| Blocking/CPU-bound work whose result you return | `run_in_threadpool` |
| Naturally async I/O (async DB driver, `httpx`) | just `await` it |

> **Tip.** The DOCX backend that powers these very docs wraps its synchronous `psycopg2` calls in `run_in_threadpool` for exactly this reason — a good real-world template for pairing Rivex with a blocking driver.

## Next

**High-Performance JSON** introduces `gen`, the Rust-native generator for building large payloads without Python object overhead.
