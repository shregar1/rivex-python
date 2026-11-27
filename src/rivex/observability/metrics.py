from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from rivex.middleware.middleware import Middleware

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
        """Increment the counter by ``amount`` for the given label values.

        When a Rust backing is available, the call is forwarded as-is.
        In the pure-Python path, ``amount`` must be non-negative and the
        counter is keyed by the tuple of label values for the configured
        label names.

        Args:
            amount: How much to add. Must be ``>= 0``. Defaults to 1.
            **labels: Label values keyed by the label names declared at
                construction time. Unrecognized keys are ignored.

        Raises:
            ValueError: When ``amount`` is negative on the pure-Python
                implementation.
        """
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
        """Render this counter in the Prometheus text exposition format.

        Emits the standard ``# HELP`` and ``# TYPE`` lines followed by
        one ``name{labels} value`` line per label combination. When no
        observations have been made, a single zero-valued line is
        emitted so consumers always see at least one sample.

        Returns:
            The full text block to concatenate into a scrape response.
        """
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
        """Build the ``{name="value", ...}`` label suffix for a sample key."""
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
        """Replace the current gauge value with ``value`` atomically."""
        if self._rust:
            self._rust.set(value)
            return
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1) -> None:
        """Add ``amount`` to the gauge (default ``+1``)."""
        if self._rust:
            self._rust.inc(amount)
            return
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1) -> None:
        """Subtract ``amount`` from the gauge (default ``-1``)."""
        if self._rust:
            self._rust.dec(amount)
            return
        with self._lock:
            self._value -= amount

    def collect(self) -> str:
        """Render the gauge in Prometheus text exposition format.

        Emits ``# HELP`` (if a description is set), ``# TYPE gauge``,
        and a single ``name value`` line for the current value.

        Returns:
            The text block for one gauge, ready to concatenate.
        """
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
        """Record a single observation ``value`` for the given label values.

        Updates the bucket count (first bucket whose upper bound
        ``>= value``), the running sum, and the total observation
        count for the label combination. Label combinations are
        allocated lazily on first use.

        Args:
            value: The observed value, typically a duration in
                seconds or a size in bytes.
            **labels: Label values keyed by the label names declared
                at construction time. Unrecognized keys are ignored.
        """
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
        """Return a context manager that records the elapsed wall time.

        Usage::

            with hist.time(method="GET"):
                do_work()

        On exit, ``time.monotonic()`` deltas are passed to
        :meth:`observe` together with the captured ``labels``.

        Args:
            **labels: Label values to apply to the recorded observation.

        Returns:
            A :class:`_HistogramTimer` context manager.
        """
        return _HistogramTimer(self, labels)

    def collect(self) -> str:
        """Render the histogram in Prometheus text exposition format.

        For every observed label combination, emits a cumulative
        ``<name>_bucket{le="..."}`` line per bucket plus an
        ``+Inf`` line, followed by ``<name>_sum`` and ``<name>_count``.

        Returns:
            The text block describing this histogram.
        """
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
        """Build the ``{name="value", ...}`` label suffix for ``key``."""
        if not self._labels:
            return ""
        pairs = ",".join(
            f'{name}="{value}"' for name, value in zip(self._labels, key, strict=False)
        )
        return "{" + pairs + "}"

    def _format_bucket_labels(self, key: tuple[str, ...], le: float | str) -> str:
        """Build the ``{name="value", ..., le="..."}`` suffix for one bucket sample.

        The numeric ``le`` upper bound is rendered through
        :func:`_format_value` so integer-looking floats (e.g. ``1.0``)
        stay compact; the ``"+Inf"`` sentinel is emitted as-is.

        Args:
            key: The label-value tuple for the current series.
            le: The bucket upper bound, either a float or the literal
                ``"+Inf"`` string.

        Returns:
            The brace-enclosed label suffix including the ``le`` entry.
        """
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
        """Create and register a new :class:`Counter` and return it.

        The counter is appended to :attr:`_metrics` so it is included
        in :meth:`collect` output. Repeated calls with the same name
        create independent counters (the registry does not dedupe).

        Args:
            name: Metric name (Prometheus convention).
            description: Optional ``HELP`` text.
            labels: Optional list of label names to declare.

        Returns:
            The newly created :class:`Counter`.
        """
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
        """Create and register a new :class:`Histogram` and return it.

        The histogram is appended to :attr:`_metrics` so it is included
        in :meth:`collect` output. ``buckets`` defaults to
        :data:`DEFAULT_BUCKETS` when ``None`` and is sorted before use.

        Args:
            name: Metric name.
            description: Optional ``HELP`` text.
            buckets: Upper bounds for the buckets.
            labels: Optional list of label names to declare.

        Returns:
            The newly created :class:`Histogram`.
        """
        h = Histogram(name, description, buckets, labels)
        self._metrics.append(h)
        return h

    def gauge(self, name: str, description: str = "") -> Gauge:
        """Create and register a new :class:`Gauge` and return it.

        Args:
            name: Metric name.
            description: Optional ``HELP`` text.

        Returns:
            The newly created :class:`Gauge`.
        """
        g = Gauge(name, description)
        self._metrics.append(g)
        return g

    def collect(self) -> str:
        """Render every registered metric into a single scrape payload.

        Each registered metric is responsible for rendering its own
        block via its own ``collect()`` method; this method simply
        joins them with blank lines and a trailing newline so the
        output is a valid Prometheus exposition document.

        Returns:
            The full Prometheus text payload.
        """
        # Each metric (Counter/Gauge/Histogram) owns its own storage — Rust-backed
        # or pure-Python — and renders itself via ``collect()``. The registry's own
        # ``self._rust`` handle has nothing registered into it (metrics are created
        # standalone), so always render from the metrics we actually hold.
        blocks = [m.collect() for m in self._metrics]
        return "\n\n".join(blocks) + "\n"

    def register_routes(self, app: Any, path: str = "/metrics") -> None:
        """Mount a ``GET path`` route on ``app`` that serves the scrape output.

        The route's response uses the Prometheus text format content
        type and excludes the endpoint from the OpenAPI schema.

        Args:
            app: The :class:`Rivex` or :class:`Router` to register the
                route on.
            path: URL path to serve the metrics from. Defaults to
                ``"/metrics"``.
        """
        registry = self

        @app.get(path, include_in_schema=False)
        def metrics_endpoint() -> dict:
            """Return the Prometheus exposition document for the registry.

            The endpoint is excluded from the OpenAPI schema and
            always responds with HTTP 200 and the
            ``text/plain; version=0.0.4`` content type.

            Returns:
                A :class:`Response` wrapping the registry's rendered
                text payload.
            """
            from rivex.http.responses import Response

            return Response(
                content=registry.collect(),
                status_code=200,
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )
            from rivex.http.responses import Response

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
        """Time the downstream chain and record request/duration metrics.

        Captures the wall-clock start, awaits the rest of the
        middleware chain, computes ``duration``, and increments the
        ``http_requests_total`` counter (labeled by method, path,
        status) plus observes the ``http_request_duration_seconds``
        histogram (labeled by method, path) before returning the
        downstream response unchanged.

        Args:
            request_data: The in-flight request envelope. The
                ``method`` and ``path`` keys are read for labels.
            call_next: Awaitable returning the downstream response
                dict. Its ``status`` is read for the status label.

        Returns:
            The downstream response dict, unmodified.
        """
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
    """Render a numeric metric value as a compact Prometheus-friendly string.

    Integers are emitted without a trailing ``.0``; floats are emitted
    via :class:`str` so the result is deterministic across runs.

    Args:
        v: The numeric value to render.

    Returns:
        The string form suitable for the text exposition format.
    """
    if v == int(v):
        return str(int(v))
    return str(v)
