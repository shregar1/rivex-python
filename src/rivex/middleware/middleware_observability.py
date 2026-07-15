"""Tier 2 observability middleware.

Each class below is a FastAPI-style marker that the SDK recognises
and translates to the corresponding Rust middleware. The Rust
implementation lives in ``rivex-middleware::observability`` and runs
on every request, including the const-router fast path that
bypasses Python entirely.

Install them exactly the way you would in FastAPI::

    from rivex.middleware.middleware_observability import (
        PrometheusMetricsMiddleware,
        TracingMiddleware,
        JsonLoggingMiddleware,
        HealthCheckMiddleware,
    )

    app.add_middleware(PrometheusMetricsMiddleware)               # /metrics
    app.add_middleware(TracingMiddleware)                       # tracing spans
    app.add_middleware(JsonLoggingMiddleware)                   # JSON access log
    app.add_middleware(HealthCheckMiddleware)                   # /healthz /readyz

Each class also implements the ``Middleware.process`` ASGI-style
interface so it continues to work when running under uvicorn (no
Rust engine in the loop).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable


# ── shared base ──────────────────────────────────────────────────────


class _BaseObservabilityMiddleware:
    """Common helpers for all Tier 2 middleware: request-id, time."""

    def _new_request_id(self) -> str:
        return f"req-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"


# ── Prometheus metrics ──────────────────────────────────────────────


class PrometheusMetricsMiddleware(_BaseObservabilityMiddleware):
    """Expose request-count / latency / in-flight gauges on
    ``/metrics`` (path configurable).

    Counter / histogram labels follow the Prometheus convention
    (low cardinality: ``method`` + ``path`` + ``status``). The
    heavy lifting (counters, histograms, encoding) is done in
    Rust; the Python class is a marker that the SDK recognises.
    """

    def __init__(
        self,
        path: str = "/metrics",
    ) -> None:
        self.path = path
        # Track per-process state for the ASGI dispatch path
        # (when running under uvicorn).
        self._counters: dict[tuple[str, str, int], int] = {}

    def process(self, request_data: dict, call_next: Callable) -> Any:
        if request_data.get("path") == self.path:
            return self._serve_metrics()
        method = request_data.get("method", "GET")
        path = request_data.get("path", "/")
        start = time.perf_counter()
        result = call_next(request_data)
        if asyncio.iscoroutine(result):
            async def _wrap() -> dict:
                resp = await result
                self._record(method, path, resp)
                return resp
            return _wrap()
        self._record(method, path, result)
        return result

    def _record(self, method: str, path: str, resp: dict) -> None:
        status = int(resp.get("status", 0))
        self._counters[(method, path, status)] = (
            self._counters.get((method, path, status), 0) + 1
        )

    def _serve_metrics(self) -> dict:
        lines = [
            "# HELP rivex_http_requests_total Total HTTP requests",
            "# TYPE rivex_http_requests_total counter",
        ]
        for (method, path, status), n in sorted(self._counters.items()):
            lines.append(
                f'rivex_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {n}'
            )
        body = "\n".join(lines) + "\n"
        return {
            "status": 200,
            "headers": [("content-type", "text/plain; version=0.0.4")],
            "body": body.encode(),
        }


# ── tracing middleware ──────────────────────────────────────────────


class TracingMiddleware(_BaseObservabilityMiddleware):
    """Wrap every request in a ``tracing`` span (``http_request``)
    and emit a single ``info!`` event on response.

    The Rust engine emits structured spans via the same
    ``tracing`` subscriber the user installed at process start.
    Python's ``logging`` integration is provided here for
    the ASGI dispatch path.
    """

    def __init__(
        self,
        span_name: str = "http_request",
    ) -> None:
        self.span_name = span_name

    def process(self, request_data: dict, call_next: Callable) -> Any:
        import logging
        method = request_data.get("method", "GET")
        path = request_data.get("path", "/")
        req_id = self._new_request_id()
        start = time.perf_counter()
        logger = logging.getLogger("rivex.access")
        logger.info(f"→ {method} {path} req_id={req_id}")
        result = call_next(request_data)
        if asyncio.iscoroutine(result):
            async def _wrap() -> dict:
                resp = await result
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                logger.info(
                    f"← {method} {path} {resp.get('status', 0)} "
                    f"{elapsed_ms:.2f}ms req_id={req_id}"
                )
                return resp
            return _wrap()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        logger.info(
            f"← {method} {path} {result.get('status', 0)} "
            f"{elapsed_ms:.2f}ms req_id={req_id}"
        )
        return result


# ── JSON logging middleware ─────────────────────────────────────────


class JsonLoggingMiddleware(_BaseObservabilityMiddleware):
    """Write one structured JSON line per request via ``logging``.

    The Rust engine emits the same JSON shape via
    ``tracing-subscriber::fmt().json()``. Use this in the ASGI
    path to keep the format consistent regardless of which engine
    is serving the app.
    """

    def __init__(self) -> None:
        pass

    def process(self, request_data: dict, call_next: Callable) -> Any:
        import json
        import logging
        method = request_data.get("method", "GET")
        path = request_data.get("path", "/")
        req_id = self._new_request_id()
        start = time.perf_counter()
        logger = logging.getLogger("rivex.json")

        def _emit(resp: dict) -> None:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.info(json.dumps({
                "event": "http_request",
                "request_id": req_id,
                "method": method,
                "path": path,
                "status": int(resp.get("status", 0)),
                "duration_ms": elapsed_ms,
                "response_size": len(resp.get("body", b"")),
            }))

        result = call_next(request_data)
        if asyncio.iscoroutine(result):
            async def _wrap() -> dict:
                resp = await result
                _emit(resp)
                return resp
            return _wrap()
        _emit(result)
        return result


# ── health check ────────────────────────────────────────────────────


class HealthCheckMiddleware(_BaseObservabilityMiddleware):
    """Auto-mount ``/healthz`` (liveness) and ``/readyz`` (readiness).

    The Rust engine serves these without going through the user
    route table, so they're always available even when the app
    hasn't registered any handler. Pass a custom ``is_ready``
    predicate to gate ``/readyz`` on downstream dependencies.
    """

    def __init__(
        self,
        liveness_path: str = "/healthz",
        readiness_path: str = "/readyz",
        is_ready: Callable[[], bool] | None = None,
    ) -> None:
        self.liveness_path = liveness_path
        self.readiness_path = readiness_path
        self._is_ready = is_ready or (lambda: True)

    def process(self, request_data: dict, call_next: Callable) -> Any:
        path = request_data.get("path", "/")
        if path == self.liveness_path:
            return self._respond(200, "ok")
        if path == self.readiness_path:
            ready = self._is_ready()
            return self._respond(200 if ready else 503, "ok" if ready else "not_ready")
        return call_next(request_data)

    def _respond(self, status: int, body: str) -> dict:
        import json
        return {
            "status": status,
            "headers": [("content-type", "application/json")],
            "body": json.dumps({"status": body}).encode(),
        }


__all__ = [
    "PrometheusMetricsMiddleware",
    "TracingMiddleware",
    "JsonLoggingMiddleware",
    "HealthCheckMiddleware",
]
