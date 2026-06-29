from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from rivex.middleware import Middleware

# ---------------------------------------------------------------------------
# Try to use Rust-backed implementations from rivex_core
# ---------------------------------------------------------------------------

try:
    from rivex_core import PyCounter as _RustCounter
    from rivex_core import PyGauge as _RustGauge
    from rivex_core import PyHistogram as _RustHistogram
    from rivex_core import PyMetricsRegistry as _RustMetricsRegistry

    _HAS_RUST = True
except ImportError:
    _HAS_RUST = False

# ---------------------------------------------------------------------------
# Default histogram buckets (matches Prometheus client defaults)
# ---------------------------------------------------------------------------

DEFAULT_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


# ---------------------------------------------------------------------------
# Counter
# ---------------------------------------------------------------------------


class Counter:
    """Prometheus-style monotonically increasing counter.

    Delegates to Rust ``PyCounter`` when available.
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        labels: list[str] | None = None,
    ):
        if _HAS_RUST:
            self._rust = _RustCounter(name, description, labels)
        else:
            self._rust = None
        self.name = name
        self.description = description
        self._labels = labels or []
        self._values: dict[tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def inc(self, amount: float = 1, **labels: str) -> None:
        if self._rust:
            label_vals = [labels.get(l, "") for l in self._labels]
            self._rust.inc(amount, label_vals if label_vals else None)
            return
        if amount < 0:
            raise ValueError("Counter increment must be non-negative")
        key = tuple(labels.get(label, "") for label in self._labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0) + amount

    def collect(self) -> str:
        if self._rust:
            return self._rust.collect()
        lines: list[str] = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} counter")
        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0")
            for key, value in sorted(self._values.items()):
                label_str = self._format_labels(key)
                lines.append(f"{self.name}{label_str} {_format_value(value)}")
        return "\n".join(lines)

    def _format_labels(self, key: tuple[str, ...]) -> str:
        if not self._labels:
            return ""
        pairs = ",".join(
            f'{name}="{value}"' for name, value in zip(self._labels, key, strict=False)
        )
        return "{" + pairs + "}"


# ---------------------------------------------------------------------------
# Gauge
# ---------------------------------------------------------------------------


class Gauge:
    """Prometheus-style gauge that can go up and down.

    Delegates to Rust ``PyGauge`` when available.
    """

    def __init__(self, name: str, description: str = ""):
        if _HAS_RUST:
            self._rust = _RustGauge(name, description)
        else:
            self._rust = None
        self.name = name
        self.description = description
        self._value: float = 0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        if self._rust:
            self._rust.set(value)
            return
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1) -> None:
        if self._rust:
            self._rust.inc(amount)
            return
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1) -> None:
        if self._rust:
            self._rust.dec(amount)
            return
        with self._lock:
            self._value -= amount

    def collect(self) -> str:
        if self._rust:
            return self._rust.collect()
        lines: list[str] = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} gauge")
        with self._lock:
            lines.append(f"{self.name} {_format_value(self._value)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


class Histogram:
    """Prometheus-style histogram with configurable buckets.

    Delegates to Rust ``PyHistogram`` when available.
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: list[float] | None = None,
        labels: list[str] | None = None,
    ):
        if _HAS_RUST:
            self._rust = _RustHistogram(name, description, buckets, labels)
        else:
            self._rust = None
        self.name = name
        self.description = description
        self._buckets = sorted(buckets or list(DEFAULT_BUCKETS))
        self._labels = labels or []
        self._bucket_counts: dict[tuple[str, ...], list[int]] = {}
        self._sums: dict[tuple[str, ...], float] = {}
        self._counts: dict[tuple[str, ...], int] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: str) -> None:
        if self._rust:
            label_vals = [labels.get(l, "") for l in self._labels]
            self._rust.observe(value, label_vals if label_vals else None)
            return
        key = tuple(labels.get(label, "") for label in self._labels)
        with self._lock:
            if key not in self._bucket_counts:
                self._bucket_counts[key] = [0] * len(self._buckets)
                self._sums[key] = 0.0
                self._counts[key] = 0
            for i, bound in enumerate(self._buckets):
                if value <= bound:
                    self._bucket_counts[key][i] += 1
                    break
            self._sums[key] += value
            self._counts[key] += 1

    def time(self, **labels: str) -> _HistogramTimer:
        return _HistogramTimer(self, labels)

    def collect(self) -> str:
        if self._rust:
            return self._rust.collect()
        lines: list[str] = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} histogram")
        with self._lock:
            for key in sorted(self._bucket_counts.keys()):
                label_str = self._format_labels(key)
                cumulative = 0
                for i, bound in enumerate(self._buckets):
                    cumulative += self._bucket_counts[key][i]
                    le_label = self._format_bucket_labels(key, bound)
                    lines.append(f"{self.name}_bucket{le_label} {cumulative}")
                inf_label = self._format_bucket_labels(key, "+Inf")
                lines.append(f"{self.name}_bucket{inf_label} {self._counts[key]}")
                lines.append(f"{self.name}_sum{label_str} {_format_value(self._sums[key])}")
                lines.append(f"{self.name}_count{label_str} {self._counts[key]}")
        return "\n".join(lines)

    def _format_labels(self, key: tuple[str, ...]) -> str:
        if not self._labels:
            return ""
        pairs = ",".join(
            f'{name}="{value}"' for name, value in zip(self._labels, key, strict=False)
        )
        return "{" + pairs + "}"

    def _format_bucket_labels(self, key: tuple[str, ...], le: float | str) -> str:
        parts: list[str] = [
            f'{name}="{value}"' for name, value in zip(self._labels, key, strict=False)
        ]
        if isinstance(le, float):
            parts.append(f'le="{_format_value(le)}"')
        else:
            parts.append(f'le="{le}"')
        return "{" + ",".join(parts) + "}"


class _HistogramTimer:
    def __init__(self, histogram: Histogram, labels: dict[str, str]):
        self._histogram = histogram
        self._labels = labels
        self._start: float = 0.0

    def __enter__(self) -> _HistogramTimer:
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc: Any) -> None:
        elapsed = time.monotonic() - self._start
        self._histogram.observe(elapsed, **self._labels)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class MetricsRegistry:
    """Central registry that owns metrics and renders them for scraping.

    Delegates to Rust ``PyMetricsRegistry`` when available.
    """

    def __init__(self) -> None:
        if _HAS_RUST:
            self._rust = _RustMetricsRegistry()
        else:
            self._rust = None
        self._metrics: list[Counter | Gauge | Histogram] = []

    def counter(
        self,
        name: str,
        description: str = "",
        labels: list[str] | None = None,
    ) -> Counter:
        c = Counter(name, description, labels)
        self._metrics.append(c)
        return c

    def histogram(
        self,
        name: str,
        description: str = "",
        buckets: list[float] | None = None,
        labels: list[str] | None = None,
    ) -> Histogram:
        h = Histogram(name, description, buckets, labels)
        self._metrics.append(h)
        return h

    def gauge(self, name: str, description: str = "") -> Gauge:
        g = Gauge(name, description)
        self._metrics.append(g)
        return g

    def collect(self) -> str:
        # Each metric (Counter/Gauge/Histogram) owns its own storage — Rust-backed
        # or pure-Python — and renders itself via ``collect()``. The registry's own
        # ``self._rust`` handle has nothing registered into it (metrics are created
        # standalone), so always render from the metrics we actually hold.
        blocks = [m.collect() for m in self._metrics]
        return "\n\n".join(blocks) + "\n"

    def register_routes(self, app: Any, path: str = "/metrics") -> None:
        registry = self

        @app.get(path, include_in_schema=False)
        def metrics_endpoint() -> dict:
            from rivex.responses import Response

            return Response(
                content=registry.collect(),
                status_code=200,
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )


# ---------------------------------------------------------------------------
# Metrics middleware
# ---------------------------------------------------------------------------


class MetricsMiddleware(Middleware):
    def __init__(self, registry: MetricsRegistry | None = None):
        self.registry = registry or MetricsRegistry()
        self._request_count = self.registry.counter(
            "http_requests_total",
            "Total HTTP requests",
            labels=["method", "path", "status"],
        )
        self._request_duration = self.registry.histogram(
            "http_request_duration_seconds",
            "Request duration in seconds",
            labels=["method", "path"],
        )

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        start = time.monotonic()
        response: dict = await call_next(request_data)
        duration = time.monotonic() - start

        method = request_data.get("method", "GET")
        path = request_data.get("path", "/")
        status = str(response.get("status", 200)) if isinstance(response, dict) else "200"

        self._request_count.inc(method=method, path=path, status=status)
        self._request_duration.observe(duration, method=method, path=path)
        return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_value(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return str(v)
