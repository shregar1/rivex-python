# Observability

Production services need to be measurable. Rivex bundles Prometheus-style metrics, distributed tracing, structured logging, and health probes — each a few lines to wire up.

## Health checks

`HealthCheck` separates **liveness** (is the process alive?) from **readiness** (can it serve traffic?), and registers standard endpoints.

```python
from rivex.health import HealthCheck

health = HealthCheck()


@health.liveness("process")
def process_alive() -> bool:
    return True


@health.readiness("database")
async def db_ready() -> bool:
    return await db.ping()


health.register_routes(app)   # serves GET /healthz and GET /readyz
```

`/healthz` returns the liveness result; `/readyz` runs the readiness checks and reports each one — point your orchestrator's probes at these.

## Metrics

Add `MetricsMiddleware` to record request metrics, and expose them in Prometheus exposition format.

```python
from rivex.metrics import MetricsRegistry, MetricsMiddleware

registry = MetricsRegistry()
app.add_middleware(MetricsMiddleware, registry=registry)
registry.register_routes(app)     # serves GET /metrics
```

Define your own instruments — counters, gauges, histograms:

```python
orders = registry.counter("orders_total", labels=["status"])
in_flight = registry.gauge("in_flight_requests")
latency = registry.histogram("handler_latency_ms", buckets=[10, 50, 100, 500])

orders.inc(status="paid")
in_flight.set(7)

with latency.time():      # times the block
    do_work()
```

`GET /metrics` yields lines like `orders_total{status="paid"} 12` for any Prometheus scraper.

## Tracing

`TracingMiddleware` creates a span per request, propagates W3C `traceparent` headers, and exports spans. Without OpenTelemetry installed it falls back to a console exporter.

```python
from rivex.tracing import configure_tracing

app.add_middleware(configure_tracing(service_name="payments-api"))
```

Or wire an exporter explicitly:

```python
from rivex.tracing import TracingMiddleware, ConsoleSpanExporter, OTelSpanExporter

app.add_middleware(
    TracingMiddleware,
    service_name="payments-api",
    exporter=OTelSpanExporter(),   # or ConsoleSpanExporter() for local dev
)
```

Each span carries `trace_id`, `span_id`, and HTTP attributes (method, path, status), ready for Jaeger, Zipkin, or an OTLP collector.

## Structured logging

Emit machine-parseable JSON logs and a structured access log:

```python
from rivex.structlog import configure_logging, StructuredAccessLogMiddleware

log = configure_logging(level="INFO", format="json")
app.add_middleware(StructuredAccessLogMiddleware)


@app.post("/login")
async def login(email: str):
    log.info("login_attempt", email=email, ip="…")
    return {"ok": True}
```

Output is JSON Lines — one object per event with your key/value context attached:

```json
{"level":"info","message":"login_attempt","timestamp":"…","email":"ada@x.io"}
{"level":"info","message":"request","method":"POST","path":"/login","status":200,"duration_ms":7.2}
```

## Events and signals

For lightweight in-process hooks, `rivex.events` exposes Django-style signals around the request lifecycle:

```python
from rivex.events import request_started, request_finished, server_startup


@request_finished.receiver()
def on_finish(sender, **kwargs):
    ...   # record, clean up, etc.
```

Signals available: `request_started`, `request_finished`, `request_failed`, `server_startup`, `server_shutdown`.

## A production middleware stack

```python
from rivex import Rivex, RequestIdMiddleware, SecurityHeadersMiddleware
from rivex.metrics import MetricsRegistry, MetricsMiddleware
from rivex.structlog import StructuredAccessLogMiddleware
from rivex.tracing import configure_tracing
from rivex.health import HealthCheck

app = Rivex(title="payments-api")
registry = MetricsRegistry()

app.add_middleware(RequestIdMiddleware)
app.add_middleware(StructuredAccessLogMiddleware)
app.add_middleware(configure_tracing(service_name="payments-api"))
app.add_middleware(MetricsMiddleware, registry=registry)
app.add_middleware(SecurityHeadersMiddleware)

registry.register_routes(app)
HealthCheck().register_routes(app)
```

## Monitoring dashboard

The `rivex_monitor` package feeds a live, per-protocol monitoring dashboard into the Rivex admin panel — HTTP routes, WebSocket connections, WebRTC peers, gRPC methods, adapter health, and more — all visible in real time.

```python
from rivex_monitor import register_monitor_partials, MonitorMiddleware

app.add_middleware(MonitorMiddleware)
register_monitor_partials(app)
```

Six admin partials are registered automatically:

| Partial | What it shows |
| --- | --- |
| `monitor_http` | Per-route: count, 4xx/5xx rate, p50/p95/p99 latency |
| `monitor_ws` | Active connections, messages/sec, error rate |
| `monitor_webrtc` | Peer count, inbound/outbound video/audio/data tracks |
| `monitor_grpc` | Per-method: calls, error rate, rolling latency quantiles |
| `monitor_adapters` | Connected protocol adapters (HTTP, WS, WebRTC, gRPC), per-adapter health |
| `monitor_health` | End-to-end aggregate: total calls, active adapters, error rate, uptime |

### Dual-write architecture

Every `observe_*` call writes to **both** a Rust-backed atomic store (via `PyPlatformMetrics` from the `rivex_core` native module) and a Python in-memory dict (`_MONITORS`). The Rust store powers cross-language visibility (Python, JS, Go, Ruby share the same process-level counters); the Python dict preserves per-channel and per-peer data the Rust store doesn't track.

```python
from rivex_monitor import MonitoredConnectionManager

# WebSocket connections are tracked automatically
manager = MonitoredConnectionManager()
await manager.connect(websocket)   # recorded in both stores
```

### Dashboard integration

Visit `/admin/monitor` in the Rivex admin dashboard to see real-time protocol metrics. Each partial is a DRF-style template fragment — the admin reads them live on every page load. The `monitor_health` action also powers the admin navbar health indicator.

When the compiled `rivex_core` extension is unavailable (development, CI), `rivex_monitor` automatically falls back to pure-Python counters — no code changes needed. Toggle with `rivex_monitor._FORCE_PYTHON` or the `FORCE_PYTHON` module export.

## Next

**Configuration & Deployment** ties it together: `Settings`, the CLI, workers, and containers.
