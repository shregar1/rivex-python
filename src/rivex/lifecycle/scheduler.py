from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from typing import Any


class Scheduler:
    """Scheduled task manager wrapping APScheduler.

    Usage::

        scheduler = Scheduler()
        scheduler.add_job(my_func, "interval", seconds=30)

    Or via decorator::

        @scheduler.cron("*/5 * * * *")
        async def my_cron():
            ...
    """

    def __init__(self):
        self._jobs: dict[str, dict] = {}

    def add_job(
        self,
        func: Callable,
        trigger: str = "interval",
        hour: int | None = None,
        minute: int | None = None,
        day_of_week: str | None = None,
        seconds: int = 0,
        args: tuple | None = None,
        id: str | None = None,
    ) -> str:
        job_id = id or f"job_{len(self._jobs)}_{func.__name__}"
        self._jobs[job_id] = {
            "func": func,
            "trigger": trigger,
            "hour": hour,
            "minute": minute,
            "day_of_week": day_of_week,
            "seconds": seconds,
            "args": args or (),
            "id": job_id,
            "next_run": None,
        }
        return job_id

    def cron(self, cron_expression: str):
        """Decorator: run on cron schedule.

        Usage::

            @scheduler.cron("*/5 * * * *")
            async def task():
                ...
        """
        parts = cron_expression.split()
        if len(parts) != 5:
            raise ValueError("Cron expression must have 5 fields")

        def decorator(func: Callable) -> Callable:
            self.add_job(
                func,
                trigger="cron",
                minute=parts[0],
                hour=parts[1],
                day_of_week=parts[4],
            )
            return func
        return decorator

    def every(self, seconds: int = 0, minutes: int = 0, hours: int = 0):
        """Decorator: run on a periodic interval.

        Usage::

            @scheduler.every(seconds=30)
            async def task():
                ...
        """
        total_seconds = seconds + minutes * 60 + hours * 3600

        def decorator(func: Callable) -> Callable:
            self.add_job(func, trigger="interval", seconds=total_seconds)
            return func
        return decorator

    def scheduled(self, schedule: str, at: str | None = None):
        """Decorator: run at a specific time daily.

        Usage::

            @scheduler.scheduled("daily", at="03:00")
            async def nightly_cleanup():
                ...
        """
        hour, minute = 0, 0
        if at and ":" in at:
            hour, minute = map(int, at.split(":"))

        def decorator(func: Callable) -> Callable:
            self.add_job(func, trigger="cron", hour=hour, minute=minute)
            return func
        return decorator

    def start(self) -> None:
        pass  # APScheduler starts automatically

    def stop(self) -> None:
        pass

    def list_jobs(self) -> list[dict]:
        return list(self._jobs.values())

    def pause_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            self._jobs[job_id]["paused"] = True
            return True
        return False

    def resume_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            self._jobs[job_id].pop("paused", None)
            return True
        return False

    def delete_job(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None
