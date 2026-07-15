from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class HealthCheck:
    """Kubernetes-style liveness/readiness health checks."""

    def __init__(self):
        self._checks: list[tuple[str, Callable, str]] = []  # (name, check_fn, check_type)

    def add_check(self, name: str, check: Callable, check_type: str = "readiness") -> None:
        """Add a health check. check_type is 'liveness' or 'readiness'."""
        self._checks.append((name, check, check_type))

    def liveness(self, name: str):
        """Decorator to register a liveness check."""

        def decorator(func):
            self.add_check(name, func, "liveness")
            return func

        return decorator

    def readiness(self, name: str):
        """Decorator to register a readiness check."""

        def decorator(func):
            self.add_check(name, func, "readiness")
            return func

        return decorator

    async def _run_checks(self, check_type: str | None = None) -> dict[str, Any]:
        results: dict[str, Any] = {}
        all_ok = True
        for name, check, ct in self._checks:
            if check_type and ct != check_type:
                continue
            try:
                result = check()
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, bool):
                    results[name] = {"status": "ok" if result else "fail"}
                    if not result:
                        all_ok = False
                elif isinstance(result, dict):
                    results[name] = result
                    if result.get("status") == "fail":
                        all_ok = False
                else:
                    results[name] = {"status": "ok"}
            except Exception as e:
                results[name] = {"status": "fail", "error": str(e)}
                all_ok = False
        return {"status": "healthy" if all_ok else "unhealthy", "checks": results}

    async def check_liveness(self) -> dict:
        """Run liveness checks. Is the process alive and not deadlocked?"""
        result = await self._run_checks("liveness")
        if not result["checks"]:
            return {"status": "healthy", "checks": {}}
        return result

    async def check_readiness(self) -> dict:
        """Run readiness checks. Can the service handle traffic?"""
        return await self._run_checks("readiness")

    async def check_all(self) -> dict:
        """Run all checks."""
        return await self._run_checks(None)

    def register_routes(
        self, app: Any, liveness_path: str = "/healthz", readiness_path: str = "/readyz"
    ) -> None:
        """Register health check routes on the app."""
        health = self

        @app.get(liveness_path, include_in_schema=False)
        async def liveness_handler():
            result = await health.check_liveness()
            status = 200 if result["status"] == "healthy" else 503
            from rivex.core.responses import JSONResponse

            return JSONResponse(result, status_code=status)

        @app.get(readiness_path, include_in_schema=False)
        async def readiness_handler():
            result = await health.check_readiness()
            status = 200 if result["status"] == "healthy" else 503
            from rivex.core.responses import JSONResponse

            return JSONResponse(result, status_code=status)
