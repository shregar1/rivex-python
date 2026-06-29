"""Concurrency utilities for CPU-bound and blocking operations.

Provides :func:`run_in_threadpool` for offloading CPU-bound work to a
thread pool while releasing the GIL, allowing other Python worker
threads to handle requests concurrently.

Usage::

    from rivex.concurrency import run_in_threadpool

    @app.get("/compute/{n}")
    async def compute(n: int):
        result = await run_in_threadpool(expensive_math, n)
        return {"result": result}
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

# Shared thread pool for CPU-bound work — threads release the GIL
# when executing native/C-extension code (math, numpy, etc.)
_CPU_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="rivex-cpu")


async def run_in_threadpool(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run *func* in a thread pool, releasing the GIL for other workers.

    Use this for CPU-bound operations that would otherwise block the
    event loop and hold the GIL, preventing other Python worker threads
    from processing requests.

    The function runs in a dedicated thread pool (separate from the
    background-task pool) and the calling coroutine is suspended until
    the result is ready.

    Parameters
    ----------
    func:
        A synchronous callable to execute in the thread pool.
    *args, **kwargs:
        Positional and keyword arguments forwarded to *func*.

    Returns
    -------
    The return value of *func(*args, **kwargs)*.

    Raises
    ------
    Any exception raised by *func* is re-raised in the caller.
    """
    loop = asyncio.get_running_loop()
    if kwargs:
        import functools

        func_with_kwargs = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(_CPU_POOL, func_with_kwargs)
    return await loop.run_in_executor(_CPU_POOL, func, *args)
