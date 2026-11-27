from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class BackgroundTask:
    __slots__ = ("func", "args", "kwargs")

    def __init__(self, func: Callable[..., Any], *args: Any, **kwargs: Any):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def __call__(self) -> None:
        if asyncio.iscoroutinefunction(self.func):
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self.func(*self.args, **self.kwargs))
            finally:
                loop.close()
        else:
            self.func(*self.args, **self.kwargs)


class BackgroundTasks:
    def __init__(self) -> None:
        self._tasks: list[BackgroundTask] = []

    def add_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Schedule *func* to be invoked after the response is sent.

        The arguments and keyword arguments are stored on the captured
        :class:`BackgroundTask` and consumed by :meth:`_run_all` once the
        main response is on the wire. Both sync and async callables are
        supported.

        Args:
            func: Callable to execute in the background.
            *args: Positional arguments forwarded to *func*.
            **kwargs: Keyword arguments forwarded to *func*.
        """
        self._tasks.append(BackgroundTask(func, *args, **kwargs))

    def _run_all(self) -> None:
        """Execute every queued background task, swallowing any error they raise.

        Failures are logged to ``stderr`` rather than propagated so a
        single faulty task never disrupts the rest of the queue or
        affects the response that has already been sent.
        """
        for task in self._tasks:
            try:
                task()
            except Exception as exc:
                import sys

                print(f"  background task error: {exc}", file=sys.stderr)
