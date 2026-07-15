from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any


class OpenTelemetryMiddleware:
    """Creates OpenTelemetry spans for every HTTP request.

    Usage::

        app.add_middleware(OpenTelemetryMiddleware, service_name="my-app")
    """

    def __init__(
        self,
        service_name: str | None = None,
        app: Any = None,
        instrument_libs: bool = True,
    ):
        self._service_name = service_name or os.environ.get("OTEL_SERVICE_NAME", "rivex-app")
        self._instrument_libs = instrument_libs

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider = TracerProvider()
            processor = BatchSpanProcessor(OTLPSpanExporter())
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(__name__)
            self._enabled = True
        except ImportError:
            self._tracer = None
            self._enabled = False

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        if not self._enabled:
            return await call_next(request_data)

        method = request_data.get("method", "GET")
        path = request_data.get("path", "/")
        start = time.time()

        with self._tracer.start_as_current_span(f"{method} {path}") as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", path)
            span.set_attribute("service.name", self._service_name)

            try:
                result = await call_next(request_data)
                duration = (time.time() - start) * 1000
                status = result.get("status", 200)
                span.set_attribute("http.status_code", status)
                span.set_attribute("http.duration_ms", duration)
                if status >= 500:
                    span.set_status(Exception(f"HTTP {status}"))
                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(e)
                raise


def configure_otel(
    service_name: str = "rivex-app",
    exporter: str = "otlp",
    endpoint: str | None = None,
    headers: dict | None = None,
) -> None:
    """One-call OpenTelemetry configuration.

    Usage::

        configure_otel(service_name="my-api", exporter="otlp")
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        provider = TracerProvider()

        if exporter == "console":
            processor = BatchSpanProcessor(ConsoleSpanExporter())
        elif exporter == "otlp":
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                exp = OTLPSpanExporter(
                    endpoint=endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"),
                    headers=headers or {},
                )
                processor = BatchSpanProcessor(exp)
            except ImportError:
                processor = BatchSpanProcessor(ConsoleSpanExporter())
        else:
            processor = BatchSpanProcessor(ConsoleSpanExporter())

        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
    except ImportError:
        pass


def set_tracer(tracer: Any) -> None:
    try:
        from opentelemetry import trace
        trace.set_tracer_provider(tracer)
    except ImportError:
        pass


def get_tracer() -> Any:
    try:
        from opentelemetry import trace
        return trace.get_tracer(__name__)
    except ImportError:
        return None
