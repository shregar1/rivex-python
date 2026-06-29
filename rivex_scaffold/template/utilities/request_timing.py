"""Per-request timing aggregation across http/controller/service/repository/utility layers."""

from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass, field
from typing import Any, Literal

TimingLayer = Literal["http", "controller", "service", "repository", "utility"]

_TIMING_LAYERS: tuple[TimingLayer, ...] = (
    "http",
    "controller",
    "service",
    "repository",
    "utility",
)

_request_timing: contextvars.ContextVar["RequestTiming | None"] = contextvars.ContextVar(
    "request_timing",
    default=None,
)


@dataclass
class TimingSpan:
    layer: TimingLayer
    operation: str
    duration_ms: float
    outcome: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class RequestTiming:
    """Collects timed spans for one HTTP request lifecycle."""

    started_at: float = field(default_factory=time.perf_counter)
    spans: list[TimingSpan] = field(default_factory=list)

    def record(
        self,
        layer: TimingLayer,
        operation: str,
        duration_ms: float,
        outcome: str,
        **fields: Any,
    ) -> None:
        cleaned = {key: value for key, value in fields.items() if value is not None}
        self.spans.append(
            TimingSpan(
                layer=layer,
                operation=operation,
                duration_ms=round(duration_ms, 2),
                outcome=outcome,
                fields=cleaned,
            )
        )

    def to_metadata(self) -> dict[str, Any]:
        layers: dict[str, Any] = {
            layer: {"duration_ms": 0.0, "count": 0, "spans": []}
            for layer in _TIMING_LAYERS
        }
        for span in self.spans:
            bucket = layers[span.layer]
            bucket["duration_ms"] = round(bucket["duration_ms"] + span.duration_ms, 2)
            bucket["count"] += 1
            bucket["spans"].append(
                {
                    "operation": span.operation,
                    "duration_ms": span.duration_ms,
                    "outcome": span.outcome,
                    **span.fields,
                }
            )

        wall_ms = round((time.perf_counter() - self.started_at) * 1000, 2)
        http_ms = layers["http"]["duration_ms"] or wall_ms
        return {
            "timing": {
                "total_ms": wall_ms,
                "http_ms": http_ms,
                "layers": layers,
            }
        }


def begin_request() -> RequestTiming:
    """Start a new request-scoped timing context."""
    ctx = RequestTiming()
    _request_timing.set(ctx)
    return ctx


def current_request_timing() -> RequestTiming | None:
    return _request_timing.get()


def end_request() -> None:
    _request_timing.set(None)


def record_layer_timing(
    layer: TimingLayer,
    operation: str,
    duration_ms: float,
    outcome: str,
    **fields: Any,
) -> None:
    ctx = _request_timing.get()
    if ctx is None:
        return
    ctx.record(layer, operation, duration_ms, outcome, **fields)


def merge_timing_metadata(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach collected layer timings to envelope metadata when present."""
    merged = dict(metadata or {})
    ctx = _request_timing.get()
    if ctx is not None and ctx.spans:
        merged.update(ctx.to_metadata())
    return merged
