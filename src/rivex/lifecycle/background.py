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
        self._tasks.append(BackgroundTask(func, *args, **kwargs))

    def _run_all(self) -> None:
        for task in self._tasks:
            try:
                task()
            except Exception as exc:
                import sys

                print(f"  background task error: {exc}", file=sys.stderr)
