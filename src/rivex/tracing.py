from __future__ import annotations

import time
import uuid
from typing import Any

from rivex._compat import get_request_header
from rivex.middleware import Middleware


class Span:
    """Lightweight span representation for tracing."""

    def __init__(self, name: str, trace_id: str, span_id: str, parent_span_id: str | None = None):
        self.name = name
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.start_time: float = time.monotonic()
        self.end_time: float | None = None
        self.attributes: dict[str, Any] = {}
        self.status: str = "ok"

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: str) -> None:
        self.status = status

    def end(self) -> None:
        self.end_time = time.monotonic()

    @property
    def duration_ms(self) -> float:
        end = self.end_time or time.monotonic()
        return (end - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "start_time": self.start_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
        }
        if self.parent_span_id:
            d["parent_span_id"] = self.parent_span_id
        return d


class SpanExporter:
    """Base exporter. Subclass to send spans to Jaeger/Zipkin/OTEL collector."""

    def export(self, spans: list[Span]) -> None:
        pass


class ConsoleSpanExporter(SpanExporter):
    """Prints spans to console as JSON."""

    def export(self, spans):
        import json

        for span in spans:
            print(json.dumps(span.to_dict(), default=str))


class OTelSpanExporter(SpanExporter):
    """Export spans to OpenTelemetry when the opentelemetry package is installed."""

    def __init__(self, service_name: str = "rivex"):
        self._tracer = None
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider

            provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(service_name)
        except ImportError:
            pass

    def export(self, spans: list[Span]) -> None:
        if self._tracer is None:
            return
        from opentelemetry import trace

        for span in spans:
            with self._tracer.start_as_current_span(
                f"{span.attributes.get('http.method', '')} {span.attributes.get('http.path', '')}",
                attributes={k: str(v) for k, v in span.attributes.items()},
            ) as otel_span:
                otel_span.set_status(
                    trace.StatusCode.OK if span.status == "ok" else trace.StatusCode.ERROR
                )


def configure_tracing(
    service_name: str = "rivex", exporter: SpanExporter | None = None
) -> TracingMiddleware:
    """Create a TracingMiddleware with sensible defaults."""
    if exporter is None:
        exporter = OTelSpanExporter(service_name)
        if exporter._tracer is None:
            exporter = ConsoleSpanExporter()
    return TracingMiddleware(exporter=exporter, service_name=service_name)


class TracingMiddleware(Middleware):
    """Distributed tracing middleware. Creates spans for each request."""

    def __init__(
        self,
        service_name: str = "rivex",
        exporter: SpanExporter | None = None,
        propagate: bool = True,
    ):
        self.service_name = service_name
        self.exporter = exporter
        self.propagate = propagate

    async def process(self, request_data, call_next):
        traceparent = get_request_header(request_data, "traceparent") or ""
        trace_id, parent_span_id = self._parse_traceparent(traceparent)
        if not trace_id:
            trace_id = uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]

        span = Span(
            name=f"{request_data.get('method', 'GET')} {request_data.get('path', '/')}",
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )
        span.set_attribute("http.method", request_data.get("method", ""))
        span.set_attribute("http.url", request_data.get("path", "/"))
        span.set_attribute("service.name", self.service_name)

        # Store span in request for handlers to access
        request_data = dict(request_data)
        request_data["_span"] = span

        try:
            response = await call_next(request_data)
            status = response.get("status", 200) if isinstance(response, dict) else 200
            span.set_attribute("http.status_code", status)
            if status >= 400:
                span.set_status("error")
            span.end()

            # Add trace headers to response for propagation
            if self.propagate and isinstance(response, dict):
                tp = f"00-{trace_id}-{span_id}-01"
                response_headers = list(response.get("headers", []))
                response_headers.append(("traceparent", tp))
                response_headers.append(("x-trace-id", trace_id))
                response["headers"] = response_headers

            if self.exporter:
                self.exporter.export([span])

            return response
        except Exception as e:
            span.set_status("error")
            span.set_attribute("error.message", str(e))
            span.end()
            if self.exporter:
                self.exporter.export([span])
            raise

    @staticmethod
    def _parse_traceparent(header: str) -> tuple[str | None, str | None]:
        """Parse W3C traceparent header: 00-{trace_id}-{parent_id}-{flags}."""
        parts = header.split("-")
        if len(parts) == 4:
            return parts[1], parts[2]
        return None, None
