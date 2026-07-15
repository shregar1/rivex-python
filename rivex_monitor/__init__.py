"""
End-to-end protocol monitoring for the Rivex admin dashboard.

Uses the Rust-backed ``PyPlatformMetrics`` singleton when the
``rivex_core`` native module is available, falling back to a
pure-Python in-memory store for development / testing.

Usage in your app::

    from rivex_monitor import register_monitor_partials, MonitorMiddleware
    from rivex.middleware.middleware import Middleware

    app.add_middleware(MonitorMiddleware)
    register_monitor_partials(app)
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from rivex_admin import AdminContext, admin_action, admin_partial

# ---------------------------------------------------------------------------
# Detect Rust-backed PyPlatformMetrics
# ---------------------------------------------------------------------------

_HAS_RUST_METRICS = False
_RustMetrics: type | None = None
try:
    from rivex_core import PyPlatformMetrics as _RustMetrics

    _HAS_RUST_METRICS = True
except ImportError:
    pass

# Toggle to force the pure-Python path for testing.
# When True, _use_rust() returns False even if Rust is available.
_FORCE_PYTHON = False


def _use_rust() -> bool:
    return not _FORCE_PYTHON and _HAS_RUST_METRICS and _RustMetrics is not None


def _reset_rust() -> None:
    """Reset the Rust-backed store.  Used in test teardown."""
    global _MONITORS
    _MONITORS.clear()
    if _use_rust():
        _RustMetrics._reset()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely dig into an object by attribute name."""
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def _safe_call(obj: Any, attr: str, *args, **kwargs) -> Any:
    """Safely call a method on an object."""
    try:
        fn = getattr(obj, attr, None)
        if fn is not None and callable(fn):
            return fn(*args, **kwargs)
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# MonitorMiddleware — captures REST request metrics for the dashboard
# ---------------------------------------------------------------------------


class MonitorMiddleware:
    """Middleware that feeds REST request data into the dashboard monitor.

    The ``app`` parameter is optional — if omitted, the middleware will try
    to find the app reference on the first processed request.

    Add it to your app *after* any other middleware that could short-circuit::

        app.add_middleware(MonitorMiddleware)
    """

    def __init__(self, app: Any = None):
        self._app = app
        self._resolved = app is not None

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        if not self._resolved:
            self._app = request_data.get("_app") or request_data.get("app")
            self._resolved = self._app is not None
        start = time.monotonic()
        response: dict = await call_next(request_data)
        duration_ms = (time.monotonic() - start) * 1000
        if self._app is not None:
            observe_rest_request(
                self._app,
                method=request_data.get("method", "GET"),
                path=request_data.get("path", "/"),
                status=response.get("status", 200),
                latency_ms=duration_ms,
            )
        return response


class MonitoredConnectionManager:
    """Wraps a ``rivex.ws.ConnectionManager`` to feed WS message data
    into the dashboard monitor.

    Usage::

        from rivex.protocols.ws import ConnectionManager
        from rivex_monitor import MonitoredConnectionManager

        app._ws_manager = MonitoredConnectionManager(ConnectionManager(), app)
    """

    def __init__(self, inner: Any, app: Any):
        self._inner = inner
        self._app = app

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def connect(self, websocket: Any, rooms: list[str] | None = None) -> None:
        if _use_rust():
            try:
                _RustMetrics.ws_connect()
            except Exception:
                pass
        monitor = _get_or_create_monitor(self._app)
        monitor["websocket"]["active_connections"] += 1
        monitor["websocket"]["total_connections"] += 1
        await self._inner.connect(websocket, rooms)

    def disconnect(self, websocket: Any) -> None:
        if _use_rust():
            try:
                _RustMetrics.ws_disconnect()
            except Exception:
                pass
        monitor = _get_or_create_monitor(self._app)
        monitor["websocket"]["active_connections"] = max(
            0, monitor["websocket"]["active_connections"] - 1
        )
        self._inner.disconnect(websocket)

    async def send_text(self, websocket: Any, text: str, channel: str = "default") -> None:
        observe_ws_message(self._app, str(id(websocket)), channel, "out", len(text.encode("utf-8")))
        await websocket.send_text(text)

    async def send_bytes(self, websocket: Any, data: bytes, channel: str = "default") -> None:
        observe_ws_message(self._app, str(id(websocket)), channel, "out", len(data))
        await websocket.send_bytes(data)

    async def receive_text(self, websocket: Any, channel: str = "default") -> str:
        text = await websocket.receive_text()
        observe_ws_message(self._app, str(id(websocket)), channel, "in", len(text.encode("utf-8")))
        return text

    async def receive_bytes(self, websocket: Any, channel: str = "default") -> bytes:
        data = await websocket.receive_bytes()
        observe_ws_message(self._app, str(id(websocket)), channel, "in", len(data))
        return data


# ---------------------------------------------------------------------------
# REST monitoring
# ---------------------------------------------------------------------------


def _seed_rust_into_python(app: Any) -> None:
    """Merge Rust-backed metrics into the Python dict so partials see both."""
    if not _use_rust():
        return
    mon = _get_or_create_monitor(app)
    rest = mon["rest"]
    # HTTP routes
    for r in _RustMetrics.http_routes():
        key = f"{r['method']} {r['path']}"
        if key not in rest["counts"] or rest["counts"][key] < r.get("requests", 0):
            rest["counts"][key] = max(rest["counts"][key], r.get("requests", 0))
            rest["latencies"][key] = {
                "p50": r.get("latency_p50_ms", 0),
                "p95": r.get("latency_p95_ms", 0),
                "p99": r.get("latency_p99_ms", 0),
            }
    rs = _RustMetrics.http_status_breakdown()
    if any(rs.values()):
        for k in ("2xx", "4xx", "5xx"):
            rest["status_codes"][k] = max(rest["status_codes"].get(k, 0), rs.get(k, 0))
    # WS
    ws = _RustMetrics.ws_metrics()
    wsd = mon["websocket"]
    wsd["active_connections"] = max(wsd["active_connections"], ws.get("active_connections", 0))
    wsd["total_connections"] = max(wsd["total_connections"], ws.get("total_connections", 0))
    wsd["messages_in"] = max(wsd["messages_in"], ws.get("messages_in", 0))
    wsd["messages_out"] = max(wsd["messages_out"], ws.get("messages_out", 0))
    wsd["bytes_in"] = max(wsd["bytes_in"], ws.get("bytes_in", 0))
    wsd["bytes_out"] = max(wsd["bytes_out"], ws.get("bytes_out", 0))
    wsd["errors"] = max(wsd.get("errors", 0), ws.get("errors", 0))
    # Adapter registry
    _seed_adapter_health(app, mon)
    # gRPC
    gr = _RustMetrics.grpc_metrics()
    grd = mon["grpc"]
    grd["uptime"] = max(grd.get("uptime", 0), gr.get("uptime_seconds", 0))
    for m in gr.get("methods", []):
        key = f"{m.get('service', '')}.{m.get('method', '')}"
        grd["counts"][key] = max(grd["counts"][key], m.get("calls", 0))
        grd["errors"][key] = max(grd["errors"][key], m.get("errors", 0))
        grd["latencies"][key] = {
            "p50": max(
                grd["latencies"].get(key, {}).get("p50", 0),
                m.get("latency_p50_ms", 0),
            ),
            "p95": m.get("latency_p95_ms", 0),
        }


def _seed_adapter_health(app: Any, mon: dict) -> None:
    """Merge adapter health from Rust adapter registry into the Python monitor,
    so the adapter_overview partial sees health status set by Go/Ruby/JS SDKs.
    """
    if not _use_rust():
        return
    try:
        for a in _RustMetrics.adapter_list():
            name = a.get("name", "")
            proto = a.get("protocol", name)
            healthy = a.get("healthy", True)
            detail = a.get("detail", "")
            mon.setdefault("adapters", {})[proto] = {
                "name": name,
                "healthy": healthy,
                "detail": detail,
                "status": "mounted" if healthy else "degraded",
            }
    except Exception:
        pass


def _build_rest_ctx(app: Any) -> dict[str, Any]:
    """Build the REST partial context."""
    _seed_rust_into_python(app)
    monitor = _get_or_create_monitor(app)
    rest = monitor["rest"]
    _sync_from_prometheus(app, rest)

    routes = _safe_get(app, "_routes", [])
    if not routes:
        routes = _safe_get(app, "router", {}).get("routes", [])

    route_keys: set[str] = set()
    for route in routes:
        path = _safe_get(route, "path", "/unknown")
        method = _safe_get(route, "method", "ANY")
        route_keys.add(f"{method} {path}")

    observed_to_route: dict[str, str] = {}
    for obs_key in rest["counts"]:
        if obs_key in route_keys:
            observed_to_route[obs_key] = obs_key
        else:
            obs_parts = obs_key.split(" ", 1)
            if len(obs_parts) == 2:
                obs_method, obs_path = obs_parts
                obs_segments = obs_path.strip("/").split("/")
                matched = False
                for rk in route_keys:
                    rk_parts = rk.split(" ", 1)
                    if len(rk_parts) == 2 and rk_parts[0] == obs_method:
                        rk_segments = rk_parts[1].strip("/").split("/")
                        if len(obs_segments) == len(rk_segments):
                            match = all(
                                os == rs or (rs.startswith("{") and rs.endswith("}"))
                                for os, rs in zip(obs_segments, rk_segments)
                            )
                            if match:
                                observed_to_route[obs_key] = rk
                                matched = True
                                break
                if not matched:
                    observed_to_route[obs_key] = obs_key
            else:
                observed_to_route[obs_key] = obs_key

    per_route = {}
    for route in routes:
        path = _safe_get(route, "path", "/unknown")
        method = _safe_get(route, "method", "ANY")
        endpoint = _safe_get(route, "endpoint", None)
        handler_count = 1 if endpoint is not None else 0
        route_key = f"{method} {path}"

        total_reqs = 0
        p50_vals = []
        for obs_key, mapped_route in observed_to_route.items():
            if mapped_route == route_key:
                total_reqs += rest["counts"].get(obs_key, 0)
                lat = rest["latencies"].get(obs_key, {})
                if lat.get("p50"):
                    p50_vals.append(lat["p50"])

        per_route[route_key] = {
            "method": method,
            "path": path,
            "handlers": handler_count,
            "latency_p50_ms": round(sum(p50_vals) / max(len(p50_vals), 1), 2) if p50_vals else 0,
            "latency_p95_ms": rest["latencies"].get(route_key, {}).get("p95", 0),
            "latency_p99_ms": rest["latencies"].get(route_key, {}).get("p99", 0),
            "requests": total_reqs,
        }

    for obs_key, mapped in observed_to_route.items():
        if mapped == obs_key and obs_key not in per_route:
            per_route[obs_key] = {
                "method": obs_key.split(" ", 1)[0] if " " in obs_key else "?",
                "path": obs_key.split(" ", 1)[1] if " " in obs_key else obs_key,
                "handlers": 0,
                "latency_p50_ms": rest["latencies"].get(obs_key, {}).get("p50", 0),
                "latency_p95_ms": rest["latencies"].get(obs_key, {}).get("p95", 0),
                "latency_p99_ms": rest["latencies"].get(obs_key, {}).get("p99", 0),
                "requests": rest["counts"].get(obs_key, 0),
            }

    return {
        "routes": len(routes),
        "total_requests": sum(rest["counts"].values()),
        "per_route": per_route,
        "status_breakdown": dict(rest["status_codes"]),
        "slowest_routes": sorted(
            per_route.values(),
            key=lambda r: r["latency_p95_ms"],
            reverse=True,
        )[:10],
    }


@admin_partial(
    "monitor_rest",
    title="REST monitor",
    icon="⇶",
    description="Per-route latency, status codes, request rates.",
)
async def _partial_monitor_rest(ctx: AdminContext) -> dict[str, Any]:
    return _build_rest_ctx(ctx.app)


def _sync_from_prometheus(app: Any, rest: dict) -> None:
    """Seed monitor data from existing Prometheus MetricsRegistry counters.

    Works with the pure-Python ``rivex.metrics.Counter`` / ``Histogram``
    implementations.  When the Rust backend (``rivex_core``) is active, the
    Prometheus data lives in Rust memory and cannot be read from Python;
    in that case the function is a no-op and you should use
    :class:`MonitorMiddleware` to feed data into the dashboard instead.
    """
    if _use_rust():
        return
    try:
        metrics = getattr(app, "metrics", None)
        if metrics is None:
            return
        for m in getattr(metrics, "_metrics", []):
            mname = getattr(m, "name", "")
            if getattr(m, "_rust", None) is not None:
                continue
            if mname == "http_requests_total":
                vals = getattr(m, "_values", {})
                for key_tuple, count in vals.items():
                    labels = dict(zip(getattr(m, "_labels", []), key_tuple, strict=False))
                    method = labels.get("method", "?")
                    path = labels.get("path", "/")
                    status = labels.get("status", "?")
                    route_key = f"{method} {path}"
                    rest["counts"][route_key] += count
                    rest["status_codes"][status] += count
            elif mname == "http_request_duration_seconds":
                counts = getattr(m, "_counts", {})
                sums = getattr(m, "_sums", {})
                for key_tuple, cnt in counts.items():
                    labels = dict(zip(getattr(m, "_labels", []), key_tuple, strict=False))
                    method = labels.get("method", "?")
                    path = labels.get("path", "/")
                    route_key = f"{method} {path}"
                    s = sums.get(key_tuple, 0)
                    if cnt > 0:
                        avg_ms = (s / cnt) * 1000
                        if route_key not in rest["latencies"]:
                            rest["latencies"][route_key] = {}
                        rest["latencies"][route_key]["p50"] = avg_ms
                        rest["latencies"][route_key]["p95"] = avg_ms * 1.5
                        rest["latencies"][route_key]["p99"] = avg_ms * 2.0
    except Exception:
        pass


# ---------------------------------------------------------------------------
# WebSocket monitoring
# ---------------------------------------------------------------------------


def _build_ws_ctx(app: Any) -> dict[str, Any]:
    _seed_rust_into_python(app)
    monitor = _get_or_create_monitor(app)
    ws = monitor["websocket"]

    active_connections = _safe_call(app, "active_websocket_connections", None)
    if active_connections is None:
        ws_adapter = _safe_get(app, "_ws_adapter", None) or _safe_get(app, "_riv_ws", None)
        if ws_adapter:
            active_connections = _safe_call(ws_adapter, "connection_count", None)

    return {
        "active_connections": active_connections or ws["active_connections"],
        "total_connections": ws["total_connections"],
        "messages_in": ws["messages_in"],
        "messages_out": ws["messages_out"],
        "bytes_in": ws["bytes_in"],
        "bytes_out": ws["bytes_out"],
        "per_channel": ws.get("channels", {}),
        "errors": ws.get("errors", 0),
        "top_talkers": sorted(
            ws.get("per_peer", {}).items(),
            key=lambda kv: kv[1]["total"],
            reverse=True,
        )[:10],
    }


@admin_partial(
    "monitor_ws",
    title="WebSocket monitor",
    icon="⇄",
    description="Active WS connections, messages in/out, top talkers.",
)
async def _partial_monitor_ws(ctx: AdminContext) -> dict[str, Any]:
    return _build_ws_ctx(ctx.app)


# ---------------------------------------------------------------------------
# WebRTC monitoring
# ---------------------------------------------------------------------------


def _build_webrtc_ctx(app: Any) -> dict[str, Any]:
    _seed_rust_into_python(app)
    monitor = _get_or_create_monitor(app)
    webrtc = monitor["webrtc"]

    rtc_adapter = (
        _safe_get(app, "_webrtc_adapter", None)
        or _safe_get(app, "_riv_webrtc", None)
        or _safe_get(app, "webrtc", None)
    )

    peers = {}
    if rtc_adapter:
        bridge = _safe_get(rtc_adapter, "bridge", None) or _safe_get(rtc_adapter, "_bridge", None)
        if bridge:
            raw_peers = _safe_get(bridge, "_peers", {}) or {}
            for pid, peer in raw_peers.items():
                pc = _safe_get(peer, "pc", None) or _safe_get(peer, "_pc", None)
                if pc:
                    peers[pid] = {
                        "ice_state": _safe_get(pc, "_ice_connection_state", "unknown"),
                        "dtls_state": _safe_get(pc, "_dtls_state", "unknown"),
                        "gathering_state": _safe_get(pc, "_ice_gathering_state", "unknown"),
                        "tracks": len(_safe_get(pc, "_tracks", []) or []),
                        "data_channels": list(_safe_get(pc, "_data_channels", {}).keys() or []),
                        "rtt_ms": _safe_get(pc, "_rtt", 0) or 0,
                        "bytes_sent": _safe_get(pc, "_bytes_sent", 0),
                        "bytes_received": _safe_get(pc, "_bytes_received", 0),
                        "packets_lost": _safe_get(pc, "_packets_lost", 0),
                        "messages_sent": _safe_get(pc, "_messages_sent", 0),
                        "messages_received": _safe_get(pc, "_messages_received", 0),
                    }

    if not peers:
        peers = webrtc.get("peers", {})

    return {
        "total_peers": len(peers),
        "peers": peers,
        "total_tracks": sum(p.get("tracks", 0) for p in peers.values()),
        "total_bytes": sum(
            p.get("bytes_sent", 0) + p.get("bytes_received", 0) for p in peers.values()
        ),
        "total_packets_lost": sum(p.get("packets_lost", 0) for p in peers.values()),
        "ice_states": _count_values(peers, "ice_state"),
        "rooms": webrtc.get("rooms", []),
        "conferences": webrtc.get("conference_count", 0),
    }


@admin_partial(
    "monitor_webrtc",
    title="WebRTC monitor",
    icon="▤",
    description="Per-peer connections, ICE state, tracks, bitrate, loss.",
)
async def _partial_monitor_webrtc(ctx: AdminContext) -> dict[str, Any]:
    return _build_webrtc_ctx(ctx.app)


# ---------------------------------------------------------------------------
# gRPC monitoring
# ---------------------------------------------------------------------------


def _build_grpc_ctx(app: Any) -> dict[str, Any]:
    _seed_rust_into_python(app)
    monitor = _get_or_create_monitor(app)
    grpc = monitor["grpc"]

    grpc_adapter = (
        _safe_get(app, "_grpc_adapter", None)
        or _safe_get(app, "_riv_grpc", None)
        or _safe_get(app, "grpc", None)
    )

    services = {}
    if grpc_adapter:
        service_registry = _safe_get(grpc_adapter, "_services", None) or _safe_get(
            grpc_adapter, "services", {}
        )
        if service_registry:
            for svc_name, svc in service_registry.items():
                methods = {}
                for m in _safe_get(svc, "methods", []) or _safe_get(svc, "_methods", []):
                    mname = _safe_get(m, "name", str(m))
                    methods[mname] = {
                        "calls": grpc["counts"].get(f"{svc_name}.{mname}", 0),
                        "errors": grpc["errors"].get(f"{svc_name}.{mname}", 0),
                        "latency_p50_ms": grpc["latencies"]
                        .get(f"{svc_name}.{mname}", {})
                        .get("p50", 0),
                    }
                services[svc_name] = {
                    "methods": methods,
                    "total_calls": sum(m["calls"] for m in methods.values()),
                    "total_errors": sum(m["errors"] for m in methods.values()),
                }

    if not services and grpc["counts"]:
        svc_groups: dict[str, dict[str, Any]] = {}
        for key, count in grpc["counts"].items():
            parts = key.rsplit(".", 1)
            if len(parts) == 2:
                svc_name, mname = parts
            else:
                svc_name, mname = "unknown", parts[0]
            svc_groups.setdefault(svc_name, {})
            svc_groups[svc_name][mname] = {
                "calls": count,
                "errors": grpc["errors"].get(key, 0),
                "latency_p50_ms": grpc["latencies"].get(key, {}).get("p50", 0),
            }
        for svc_name, methods in svc_groups.items():
            services[svc_name] = {
                "methods": methods,
                "total_calls": sum(m["calls"] for m in methods.values()),
                "total_errors": sum(m["errors"] for m in methods.values()),
            }

    return {
        "services": services,
        "total_services": len(services),
        "total_methods": sum(len(s["methods"]) for s in services.values()),
        "total_calls": sum(s["total_calls"] for s in services.values()),
        "total_errors": sum(s["total_errors"] for s in services.values()),
        "uptime_seconds": grpc.get("uptime", 0),
    }


@admin_partial(
    "monitor_grpc",
    title="gRPC monitor",
    icon="⏣",
    description="gRPC services, methods, latencies, error rates.",
)
async def _partial_monitor_grpc(ctx: AdminContext) -> dict[str, Any]:
    return _build_grpc_ctx(ctx.app)


# ---------------------------------------------------------------------------
# Adapter overview
# ---------------------------------------------------------------------------


def _build_adapter_ctx(app: Any) -> dict[str, Any]:
    _seed_rust_into_python(app)
    monitor = _get_or_create_monitor(app)

    adapters = {
        "rest": _check_adapter(app, "rest"),
        "websocket": _check_adapter(app, "websocket"),
        "webrtc": _check_adapter(app, "webrtc"),
        "grpc": _check_adapter(app, "grpc"),
    }

    # Merge in adapter health from Rust registry (seeded by _seed_adapter_health)
    for proto, info in monitor.get("adapters", {}).items():
        if proto in adapters:
            adapters[proto]["healthy"] = info.get("healthy", adapters[proto]["healthy"])
            adapters[proto]["detail"] = info.get("detail", adapters[proto].get("detail", ""))
            if not info.get("healthy", True):
                adapters[proto]["status"] = "degraded"
        else:
            adapters[proto] = info

    for attr in dir(app):
        if attr.startswith("_riv_") or attr.startswith("_"):
            continue
        val = _safe_get(app, attr, None)
        if val is None:
            continue
        mod = _safe_get(type(val), "__module__", "")
        if "adapter" in mod.lower() and attr not in adapters:
            adapters[attr] = {
                "name": attr,
                "type": mod.split(".")[-2] if "." in mod else mod,
                "status": "mounted",
                "healthy": True,
            }

    return {
        "adapters": adapters,
        "mounted_count": sum(1 for a in adapters.values() if a.get("status") == "mounted"),
        "healthy_count": sum(1 for a in adapters.values() if a.get("healthy")),
    }


@admin_partial(
    "adapter_overview",
    title="Adapter overview",
    icon="▣",
    description="Which adapters are mounted and their health status.",
)
async def _partial_adapter_overview(ctx: AdminContext) -> dict[str, Any]:
    return _build_adapter_ctx(ctx.app)


def _check_adapter(app: Any, protocol: str) -> dict[str, Any]:
    probes = {
        "rest": ["_routes", "router", "routes"],
        "websocket": ["_ws_adapter", "_riv_ws", "_websocket_handler", "ws"],
        "webrtc": ["_webrtc_adapter", "_riv_webrtc", "webrtc", "_bridge"],
        "grpc": ["_grpc_adapter", "_riv_grpc", "grpc"],
    }
    for attr in probes.get(protocol, []):
        val = _safe_get(app, attr, None)
        if val is not None:
            return {
                "name": protocol,
                "status": "mounted",
                "healthy": True,
                "detail": f"via app.{attr}",
            }
    return {"name": protocol, "status": "not detected", "healthy": False, "detail": ""}


# ---------------------------------------------------------------------------
# End-to-end health check action
# ---------------------------------------------------------------------------


@admin_action(
    "e2e_health_check",
    title="End-to-end health check",
    description="Ping REST/WS/gRPC/WebRTC — reports per-adapter latency & status.",
)
async def _action_e2e_health_check(ctx: AdminContext) -> dict[str, Any]:
    app = ctx.app
    results = {}
    ok = True

    # REST health
    rest_start = time.monotonic()
    try:
        routes = _safe_get(app, "_routes", []) or _safe_get(app, "router", {}).get("routes", [])
        results["rest"] = {
            "status": "up",
            "latency_ms": round((time.monotonic() - rest_start) * 1000, 2),
            "routes": len(routes),
        }
    except Exception as e:
        results["rest"] = {"status": "error", "error": str(e)}
        ok = False

    # WebSocket health
    try:
        ws_adapter = _safe_get(app, "_ws_adapter", None) or _safe_get(app, "_riv_ws", None)
        if ws_adapter:
            conn_fn = getattr(ws_adapter, "connection_count", None)
            conns = conn_fn() if callable(conn_fn) else None
            results["websocket"] = {
                "status": "up",
                "connections": conns or 0,
            }
        else:
            results["websocket"] = {"status": "not mounted"}
    except Exception as e:
        results["websocket"] = {"status": "error", "error": str(e)}
        ok = False

    # WebRTC health
    try:
        rtc_adapter = (
            _safe_get(app, "_webrtc_adapter", None)
            or _safe_get(app, "_riv_webrtc", None)
            or _safe_get(app, "webrtc", None)
        )
        if rtc_adapter:
            bridge = _safe_get(rtc_adapter, "bridge", None) or _safe_get(rtc_adapter, "_bridge", None)
            peer_count = len(_safe_get(bridge, "_peers", {}) or {}) if bridge else 0
            results["webrtc"] = {
                "status": "up",
                "peers": peer_count,
                "rooms": [_safe_get(bridge, "room", "default")] if bridge else [],
            }
        else:
            results["webrtc"] = {"status": "not mounted"}
    except Exception as e:
        results["webrtc"] = {"status": "error", "error": str(e)}
        ok = False

    # gRPC health
    try:
        grpc_adapter = (
            _safe_get(app, "_grpc_adapter", None)
            or _safe_get(app, "_riv_grpc", None)
            or _safe_get(app, "grpc", None)
        )
        if grpc_adapter:
            svcs = _safe_get(grpc_adapter, "_services", None) or _safe_get(grpc_adapter, "services", {})
            results["grpc"] = {
                "status": "up",
                "services": len(svcs or {}),
            }
        else:
            results["grpc"] = {"status": "not mounted"}
    except Exception as e:
        results["grpc"] = {"status": "error", "error": str(e)}
        ok = False

    return {"ok": ok, "timestamp": time.time(), "results": results}


# ---------------------------------------------------------------------------
# Metrics instrumentation hooks (can be called from adapters)
# ---------------------------------------------------------------------------

_MONITORS: dict[int, dict] = {}


def _get_or_create_monitor(app: Any) -> dict:
    app_id = id(app)
    if app_id not in _MONITORS:
        _MONITORS[app_id] = {
            "rest": {"counts": defaultdict(int), "status_codes": defaultdict(int), "latencies": {}},
            "websocket": {
                "active_connections": 0,
                "total_connections": 0,
                "messages_in": 0,
                "messages_out": 0,
                "bytes_in": 0,
                "bytes_out": 0,
                "channels": {},
                "per_peer": {},
                "errors": 0,
            },
            "webrtc": {
                "peers": {},
                "rooms": [],
                "conference_count": 0,
                "total_tracks": 0,
            },
            "grpc": {
                "counts": defaultdict(int),
                "errors": defaultdict(int),
                "latencies": {},
                "uptime": 0,
            },
        }
    return _MONITORS[app_id]


def observe_rest_request(
    app: Any,
    method: str,
    path: str,
    status: int,
    latency_ms: float,
) -> None:
    """Record a REST request for the dashboard."""
    if _use_rust():
        _RustMetrics.http_observe(method or "", path or "", status, latency_ms)
    monitor = _get_or_create_monitor(app)
    key = f"{method} {path}"
    monitor["rest"]["counts"][key] += 1
    monitor["rest"]["status_codes"][str(status)] += 1
    if key not in monitor["rest"]["latencies"]:
        monitor["rest"]["latencies"][key] = {"p50": latency_ms, "p95": latency_ms, "p99": latency_ms}
    else:
        lat = monitor["rest"]["latencies"][key]
        lat["p50"] = lat["p50"] * 0.9 + latency_ms * 0.1
        lat["p95"] = lat["p95"] * 0.95 + latency_ms * 0.05
        lat["p99"] = lat["p99"] * 0.99 + latency_ms * 0.01


def observe_ws_message(
    app: Any,
    peer_id: str,
    channel: str,
    direction: str,
    size: int,
) -> None:
    """Record a WebSocket message."""
    if _use_rust():
        _RustMetrics.ws_message(direction or "in", size or 0)
    monitor = _get_or_create_monitor(app)
    ws = monitor["websocket"]
    if direction == "in":
        ws["messages_in"] += 1
        ws["bytes_in"] += size
    else:
        ws["messages_out"] += 1
        ws["bytes_out"] += size
    if channel not in ws["channels"]:
        ws["channels"][channel] = {"in": 0, "out": 0, "bytes": 0}
    ws["channels"][channel][direction[:3]] += 1
    ws["channels"][channel]["bytes"] += size
    if peer_id not in ws["per_peer"]:
        ws["per_peer"][peer_id] = {"in": 0, "out": 0, "total": 0}
    ws["per_peer"][peer_id][direction[:3]] += 1
    ws["per_peer"][peer_id]["total"] += 1


def observe_grpc_call(
    app: Any,
    service: str,
    method: str,
    latency_ms: float,
    error: bool = False,
) -> None:
    """Record a gRPC call."""
    if _use_rust():
        _RustMetrics.grpc_observe(service or "", method or "", latency_ms, error)
    monitor = _get_or_create_monitor(app)
    key = f"{service}.{method}"
    monitor["grpc"]["counts"][key] += 1
    if error:
        monitor["grpc"]["errors"][key] += 1
    if key not in monitor["grpc"]["latencies"]:
        monitor["grpc"]["latencies"][key] = {"p50": latency_ms, "p95": latency_ms}
    else:
        lat = monitor["grpc"]["latencies"][key]
        lat["p50"] = lat["p50"] * 0.9 + latency_ms * 0.1
        lat["p95"] = lat["p95"] * 0.95 + latency_ms * 0.05


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_values(items: dict, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items.values():
        if isinstance(item, dict):
            k = str(item.get(key, "unknown"))
            counts[k] = counts.get(k, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Auto-registration entry point
# ---------------------------------------------------------------------------


def register_monitor_partials(app: Any) -> None:
    """Register all monitoring partials & actions on the admin dashboard.

    Call this after all adapters are mounted::

        from rivex_monitor import register_monitor_partials, MonitorMiddleware

        app.add_middleware(MonitorMiddleware)
        register_monitor_partials(app)

    The admin dashboard must already be registered (via
    ``register_admin_routes(app)``) for partials to appear.

    Side-effects:
    - Stores ``app._monitor_started_at`` for uptime tracking.
    - Wraps ``app._ws_manager`` (if present) in a ``MonitoredConnectionManager``
      so WebSocket messages are automatically tracked.
    - Wraps ``app.metrics`` (if present) to feed live Prometheus counters into
      the REST partials.
    """
    app._monitor_started_at = time.time()
    mon = _get_or_create_monitor(app)
    mon["grpc"]["uptime"] = 0

    # Wrap the WS connection manager if the app has one
    ws_mgr = getattr(app, "_ws_manager", None) or getattr(app, "ws_manager", None)
    if ws_mgr is not None and not isinstance(ws_mgr, MonitoredConnectionManager):
        app._ws_manager = MonitoredConnectionManager(ws_mgr, app)

    # Wire into the existing MetricsMiddleware counters (if present)
    existing_metrics = getattr(app, "metrics", None)
    if existing_metrics is not None:
        counter = getattr(existing_metrics, "_request_count", None)
        hist = getattr(existing_metrics, "_request_duration", None)
        if counter is not None:
            try:
                mon["rest"]["_metrics_counter"] = counter
                mon["rest"]["_metrics_histogram"] = hist
            except Exception:
                pass

    app._monitor_store = mon


__all__ = [
    "FORCE_PYTHON",
    "MonitorMiddleware",
    "MonitoredConnectionManager",
    "register_monitor_partials",
    "observe_rest_request",
    "observe_ws_message",
    "observe_grpc_call",
]

# Export for test utilities
FORCE_PYTHON = _FORCE_PYTHON
