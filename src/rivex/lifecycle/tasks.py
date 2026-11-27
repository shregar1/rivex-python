from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any


class TaskQueue(ABC):
    """Abstract task queue interface."""

    @abstractmethod
    async def enqueue(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        """Submit *task_name* to the queue and return an opaque task id.

        Args:
            task_name: Logical name of the registered task handler to invoke.
            *args: Positional arguments forwarded to the handler.
            **kwargs: Keyword arguments forwarded to the handler.

        Returns:
            An identifier the caller can later pass to :meth:`result` to
            retrieve the task's outcome.
        """
        ...

    @abstractmethod
    async def dequeue(self, timeout: float = 5.0) -> Any | None:
        """Block until a queued task is available or *timeout* elapses.

        Args:
            timeout: Maximum number of seconds to wait for a task before
                giving up.

        Returns:
            The next :class:`Task` (or backend-specific equivalent) from the
            queue, or ``None`` if the wait timed out without any task
            becoming available.
        """
        ...

    @abstractmethod
    async def result(self, task_id: str, timeout: float | None = None) -> Any | None:
        """Return the eventual result of the task identified by *task_id*.

        Args:
            task_id: Identifier returned by :meth:`enqueue` for the task to
                look up.
            timeout: Optional upper bound, in seconds, to wait for the task
                to finish. ``None`` returns whatever the backend currently
                holds without polling.

        Returns:
            The task's return value, ``None`` if it has not finished yet
            within the deadline, or raises if the task failed.
        """
        ...

    @abstractmethod
    async def length(self) -> int:
        """Return the number of tasks currently waiting in the queue."""
        ...

    @abstractmethod
    async def flush(self) -> None:
        """Discard all queued tasks without executing them."""
        ...


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    status: str = "pending"
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)


class SimpleTaskQueue(TaskQueue):
    """In-process task queue with background worker threads."""

    def __init__(self, max_workers: int = 4):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._results: dict[str, Task] = {}
        self._workers: list[threading.Thread] = []
        self._running = False
        self._handlers: dict[str, Callable] = {}
        self._max_workers = max_workers

    def register(self, name: str, handler: Callable) -> None:
        """Register *handler* as the implementation for task *name*.

        Args:
            name: Task name that callers will pass to :meth:`enqueue`.
            handler: Callable invoked with the task's args and kwargs. May
                be a regular function or a coroutine function; both are
                supported by the worker loop.
        """
        self._handlers[name] = handler

    def handler(self, name: str):
        """Return a decorator that registers its target as the handler for *name*.

        This is the decorator-style counterpart to :meth:`register` and is
        convenient for attaching task implementations directly to their
        definitions::

            @queue.handler("send_email")
            async def send_email(to: str):
                ...

        Args:
            name: Task name to associate with the decorated function.

        Returns:
            A decorator that registers the function and returns it
            unchanged so the original name and docstring are preserved.
        """
        def decorator(func):
            """Register *func* under the captured task *name* and return it."""
            self.register(name, func)
            return func
        return decorator

    async def enqueue(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        """Submit *task_name* for asynchronous execution by the worker pool.

        Wraps the call in a :class:`Task`, stores it in the results table so
        :meth:`result` can look it up later, and puts it on the internal
        queue for one of the worker threads to pick up.

        Args:
            task_name: Name of a previously registered handler.
            *args: Positional arguments forwarded to the handler.
            **kwargs: Keyword arguments forwarded to the handler.

        Returns:
            The newly generated :class:`Task` id, which can be passed to
            :meth:`result` to await the outcome.
        """
        task = Task(name=task_name, args=args, kwargs=kwargs)
        self._results[task.id] = task
        await self._queue.put(task)
        return task.id

    async def dequeue(self, timeout: float = 5.0) -> Task | None:
        """Return the next queued :class:`Task` or ``None`` after *timeout*."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def result(self, task_id: str, timeout: float | None = None) -> Any | None:
        """Look up the stored result for *task_id* and return it if available.

        The in-memory implementation does not support polling and therefore
        ignores *timeout*; it only inspects the most recently recorded
        status of the task. Completed tasks return their stored value,
        failed tasks re-raise the captured error, and still-pending tasks
        return ``None``.

        Args:
            task_id: Identifier returned by :meth:`enqueue`.
            timeout: Accepted for interface compatibility; unused here.

        Returns:
            The handler's return value, ``None`` if the task is still
            pending, or raises :class:`RuntimeError` for tasks that failed.
        """
        task = self._results.get(task_id)
        if task is None:
            return None
        if task.status == "completed":
            return task.result
        if task.status == "failed":
            raise RuntimeError(task.error)
        return None

    async def length(self) -> int:
        """Return the current number of tasks waiting on the internal queue."""
        return self._queue.qsize()

    async def flush(self) -> None:
        """Drain all pending tasks from the queue without running them."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _worker_loop(self) -> None:
        """Pull tasks off the queue and dispatch them to their registered handlers.

        Each worker thread owns its own asyncio event loop and uses
        :meth:`dequeue` with a short timeout so the loop can observe the
        :attr:`_running` flag and exit cleanly on :meth:`stop`. Handler
        exceptions are captured onto the :class:`Task` instead of
        propagating so one failing task does not kill the worker.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while self._running:
            task = loop.run_until_complete(self.dequeue(timeout=1.0))
            if task is None:
                continue
            handler = self._handlers.get(task.name)
            if handler is None:
                task.status = "failed"
                task.error = f"No handler registered for {task.name}"
                continue
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = loop.run_until_complete(handler(*task.args, **task.kwargs))
                else:
                    result = handler(*task.args, **task.kwargs)
                task.result = result
                task.status = "completed"
            except Exception as e:
                task.status = "failed"
                task.error = str(e)

    def start(self) -> None:
        """Launch the configured number of background worker threads.

        Sets :attr:`_running` to ``True`` and spawns :attr:`_max_workers`
        daemon threads, each running :meth:`_worker_loop`. Calling ``start``
        more than once will spawn additional threads; pair each ``start``
        with a matching :meth:`stop` to avoid leaking them.
        """
        self._running = True
        for _ in range(self._max_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            self._workers.append(t)

    def stop(self) -> None:
        """Signal the worker threads to stop and wait briefly for them to exit.

        Flips :attr:`_running` to ``False`` and joins every thread with a
        hard two-second cap, after which any still-running worker is left
        to exit on its own next iteration.
        """
        self._running = False
        for w in self._workers:
            w.join(timeout=2.0)


class CeleryTaskQueue(TaskQueue):
    """Celery integration adapter."""

    def __init__(self, app):
        self._celery = app

    async def enqueue(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        """Dispatch *task_name* to Celery and return the Celery task id.

        Args:
            task_name: Celery task name to invoke.
            *args: Positional arguments passed to the Celery task.
            **kwargs: Keyword arguments passed to the Celery task.

        Returns:
            The Celery-generated task id suitable for use with
            :meth:`result`.
        """
        result = self._celery.send_task(task_name, args=args, kwargs=kwargs)
        return result.id

    async def dequeue(self, timeout: float = 5.0) -> Any | None:
        """Raise — Celery owns its worker pool and does not expose dequeue."""
        raise NotImplementedError("Celery manages its own worker pool")

    async def result(self, task_id: str, timeout: float | None = None) -> Any | None:
        """Return the eventual result of the Celery task identified by *task_id*.

        If *timeout* is given, blocks the current thread for up to that
        many seconds waiting for the Celery ``AsyncResult`` to complete.
        Otherwise returns whatever Celery currently holds, which may still
        be the ``PENDING`` sentinel.

        Args:
            task_id: Celery task id returned by :meth:`enqueue`.
            timeout: Optional blocking wait in seconds.

        Returns:
            The task's return value, or the underlying ``AsyncResult``
            value when no timeout is supplied.
        """
        from celery.result import AsyncResult
        res = AsyncResult(task_id, app=self._celery)
        if timeout:
            return res.get(timeout=timeout)
        return res.result

    async def length(self) -> int:
        """Raise — Celery does not expose a synchronous queue length."""
        raise NotImplementedError

    async def flush(self) -> None:
        """No-op — Celery tasks cannot be flushed from this adapter."""
        pass


class RQTaskQueue(TaskQueue):
    """RQ (Redis Queue) integration adapter."""

    def __init__(self, queue):
        self._queue = queue

    async def enqueue(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        """Enqueue *task_name* on the underlying RQ queue and return its job id.

        Args:
            task_name: Fully-qualified RQ task name to invoke.
            *args: Positional arguments forwarded to the task.
            **kwargs: Keyword arguments forwarded to the task.

        Returns:
            The RQ ``Job`` id, which can be used to fetch the result with
            :meth:`result`.
        """
        from rq.job import Job
        job = self._queue.enqueue(task_name, args=args, kwargs=kwargs)
        return job.id

    async def dequeue(self, timeout: float = 5.0) -> Any | None:
        """Raise — RQ manages its own workers and does not expose dequeue."""
        raise NotImplementedError

    async def result(self, task_id: str, timeout: float | None = None) -> Any | None:
        """Return the result of the RQ job identified by *task_id*.

        When *timeout* is given, polls the job every half second up to the
        deadline and returns ``None`` if the job still has no result. The
        ``timeout`` argument is required to enable polling; without it the
        currently cached value is returned immediately.

        Args:
            task_id: RQ job id returned by :meth:`enqueue`.
            timeout: Optional polling deadline in seconds.

        Returns:
            The job's stored result, or ``None`` when the timeout elapses
            before the job produces one.
        """
        from rq.job import Job
        job = Job.fetch(task_id, connection=self._queue.connection)
        if timeout:
            job.refresh()
            count = 0
            while job.result is None and job.is_finished is False:
                if count * 0.5 >= timeout:
                    return None
                await asyncio.sleep(0.5)
                job.refresh()
                count += 1
        return job.result

    async def length(self) -> int:
        """Return the number of jobs currently registered in the RQ queue."""
        return len(self._queue)

    async def flush(self) -> None:
        """Remove every job from the RQ queue without executing them."""
        self._queue.empty()


def task(queue: TaskQueue | None = None):
    """Decorator that registers a function as a background task.

    Usage::

        @app.task()
        async def send_email(to: str, subject: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        """Wrap *func* so calls go through the supplied *queue* when given.

        The wrapped function's ``__name__`` is used as the task name when
        registering with the queue. The returned wrapper publishes
        ``_is_task`` and ``_task_name`` attributes so callers can detect
        task-wrapped functions via introspection.

        Args:
            func: The async function to wrap.

        Returns:
            An async wrapper that, when *queue* is set, dispatches the call
            through :meth:`TaskQueue.enqueue`; otherwise it forwards the
            call directly to *func*.
        """
        task_name = func.__name__
        if queue:
            queue.register(task_name, func)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            """Forward the call through *queue* when available, else to *func*."""
            if queue:
                return await queue.enqueue(task_name, *args, **kwargs)
            return await func(*args, **kwargs)

        wrapper._is_task = True
        wrapper._task_name = task_name
        return wrapper
    return decorator
