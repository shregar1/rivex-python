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
        ...

    @abstractmethod
    async def dequeue(self, timeout: float = 5.0) -> Any | None:
        ...

    @abstractmethod
    async def result(self, task_id: str, timeout: float | None = None) -> Any | None:
        ...

    @abstractmethod
    async def length(self) -> int:
        ...

    @abstractmethod
    async def flush(self) -> None:
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
        self._handlers[name] = handler

    def handler(self, name: str):
        def decorator(func):
            self.register(name, func)
            return func
        return decorator

    async def enqueue(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        task = Task(name=task_name, args=args, kwargs=kwargs)
        self._results[task.id] = task
        await self._queue.put(task)
        return task.id

    async def dequeue(self, timeout: float = 5.0) -> Task | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def result(self, task_id: str, timeout: float | None = None) -> Any | None:
        task = self._results.get(task_id)
        if task is None:
            return None
        if task.status == "completed":
            return task.result
        if task.status == "failed":
            raise RuntimeError(task.error)
        return None

    async def length(self) -> int:
        return self._queue.qsize()

    async def flush(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _worker_loop(self) -> None:
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
        self._running = True
        for _ in range(self._max_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            self._workers.append(t)

    def stop(self) -> None:
        self._running = False
        for w in self._workers:
            w.join(timeout=2.0)


class CeleryTaskQueue(TaskQueue):
    """Celery integration adapter."""

    def __init__(self, app):
        self._celery = app

    async def enqueue(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        result = self._celery.send_task(task_name, args=args, kwargs=kwargs)
        return result.id

    async def dequeue(self, timeout: float = 5.0) -> Any | None:
        raise NotImplementedError("Celery manages its own worker pool")

    async def result(self, task_id: str, timeout: float | None = None) -> Any | None:
        from celery.result import AsyncResult
        res = AsyncResult(task_id, app=self._celery)
        if timeout:
            return res.get(timeout=timeout)
        return res.result

    async def length(self) -> int:
        raise NotImplementedError

    async def flush(self) -> None:
        pass


class RQTaskQueue(TaskQueue):
    """RQ (Redis Queue) integration adapter."""

    def __init__(self, queue):
        self._queue = queue

    async def enqueue(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        from rq.job import Job
        job = self._queue.enqueue(task_name, args=args, kwargs=kwargs)
        return job.id

    async def dequeue(self, timeout: float = 5.0) -> Any | None:
        raise NotImplementedError

    async def result(self, task_id: str, timeout: float | None = None) -> Any | None:
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
        return len(self._queue)

    async def flush(self) -> None:
        self._queue.empty()


def task(queue: TaskQueue | None = None):
    """Decorator that registers a function as a background task.

    Usage::

        @app.task()
        async def send_email(to: str, subject: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        task_name = func.__name__
        if queue:
            queue.register(task_name, func)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            if queue:
                return await queue.enqueue(task_name, *args, **kwargs)
            return await func(*args, **kwargs)

        wrapper._is_task = True
        wrapper._task_name = task_name
        return wrapper
    return decorator
