"""Comprehensive end-to-end tests for rivex_monitor."""
from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from rivex import Rivex
from rivex_admin import AdminContext, _REGISTRY

# Module to test — loaded after imports so __init__.py can resolve
# its own imports against installed packages.
from rivex_monitor import (
    MonitorMiddleware,
    MonitoredConnectionManager,
    _get_or_create_monitor,
    _reset_rust,
    observe_rest_request,
    observe_ws_message,
    observe_grpc_call,
    register_monitor_partials,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_rust_before_each():
    """Clear the Rust-backed singleton between tests so state doesn't bleed."""
    _reset_rust()


@pytest.fixture
def app():
    a = Rivex(title="Test", version="0.1.0", admin_url="/admin", admin_db=":memory:")

    @a.get("/hello/{name}")
    async def hello(name: str):
        return {"msg": f"Hello {name}"}

    @a.get("/items")
    async def list_items():
        return []

    @a.post("/items")
    async def create_item():
        return {"id": 1}

    return a


@pytest.fixture
def ctx(app):
    register_monitor_partials(app)
    return AdminContext(app=app)


@pytest.fixture
def populated_ctx(ctx):
    """Context with realistic data pre-loaded."""
    app = ctx.app

    # REST requests (mix of success and errors)
    for _ in range(50):
        observe_rest_request(app, "GET", "/hello/world", 200, 5.0)
    for _ in range(20):
        observe_rest_request(app, "GET", "/hello/world", 200, 8.0)
    for _ in range(10):
        observe_rest_request(app, "GET", "/items", 200, 2.0)
    for _ in range(5):
        observe_rest_request(app, "POST", "/items", 201, 15.0)
    for _ in range(3):
        observe_rest_request(app, "GET", "/hello/error", 500, 200.0)

    # WebSocket messages
    observe_ws_message(app, "alice", "room:lobby", "in", 50)
    observe_ws_message(app, "alice", "room:lobby", "in", 120)
    observe_ws_message(app, "alice", "room:lobby", "out", 30)
    observe_ws_message(app, "bob", "room:lobby", "in", 80)
    observe_ws_message(app, "bob", "dm:alice", "in", 200)
    observe_ws_message(app, "charlie", "room:lobby", "in", 64)
    observe_ws_message(app, "charlie", "room:lobby", "out", 45)

    for _ in range(5):
        observe_ws_message(app, "alice", "room:lobby", "in", 10)

    # gRPC calls
    observe_grpc_call(app, "helloworld.Greeter", "SayHello", 3.2)
    observe_grpc_call(app, "helloworld.Greeter", "SayHello", 8.7)
    observe_grpc_call(app, "helloworld.Greeter", "SayHello", 12.5)
    observe_grpc_call(app, "helloworld.Greeter", "SayBye", 2.1, error=True)
    observe_grpc_call(app, "grpc.health.v1.Health", "Check", 1.0)

    return ctx


# ---------------------------------------------------------------------------
# 1. REST Monitor — guardrails, edge cases, and real data
# ---------------------------------------------------------------------------


class TestMonitorRest:
    async def _fetch(self, ctx):
        return await _REGISTRY.partials["monitor_rest"](ctx)

    def test_empty(self, ctx):
        """No data recorded — all zeros, but no crash."""
        d = asyncio.run(self._fetch(ctx))
        assert d["routes"] >= 1  # app has routes
        assert d["total_requests"] == 0
        assert d["status_breakdown"] == {}

    def test_with_data(self, populated_ctx):
        d = asyncio.run(self._fetch(populated_ctx))
        assert d["total_requests"] == 88, f"got {d['total_requests']}"
        assert d["status_breakdown"].get("200", 0) == 80
        assert d["status_breakdown"].get("201", 0) == 5
        assert d["status_breakdown"].get("500", 0) == 3

        # The un-matched paths (/hello/error, /items) sort by p95 which is 0
        # for unmatched routes (latency EWMA computed from actual paths).
        # Ensure we have entries for all observed routes.
        paths = [r["path"] for r in d["slowest_routes"]]
        assert any("/hello/error" in p or "/hello/{name}" in p for p in paths)

    def test_route_count(self, ctx, app):
        """Partial should discover app._routes."""
        before = len(app._routes)
        d = asyncio.run(self._fetch(ctx))
        assert d["routes"] == before

    def test_missing_app_routes(self, ctx):
        """Fallback when app has no _routes."""
        del ctx.app._routes
        d = asyncio.run(self._fetch(ctx))
        assert d["routes"] == 0  # graceful fallback
        assert d["per_route"] == {}

    def test_no_crash_on_non_dict_latencies(self, ctx):
        """observe_rest_request with unusual paths should not crash."""
        observe_rest_request(ctx.app, "", "", 999, 0.0)
        observe_rest_request(ctx.app, "INVALID", None, 200, 1.0)  # type: ignore[arg-type]
        d = asyncio.run(self._fetch(ctx))
        assert d["total_requests"] >= 2


# ---------------------------------------------------------------------------
# 2. WebSocket Monitor
# ---------------------------------------------------------------------------


class TestMonitorWs:
    async def _fetch(self, ctx):
        return await _REGISTRY.partials["monitor_ws"](ctx)

    def test_empty(self, ctx):
        d = asyncio.run(self._fetch(ctx))
        assert d["messages_in"] == 0
        assert d["messages_out"] == 0
        assert d["per_channel"] == {}

    def test_with_data(self, populated_ctx):
        d = asyncio.run(self._fetch(populated_ctx))
        # 5 explicit "in" messages + 5 from loop = 10
        assert d["messages_in"] == 10, f"got {d['messages_in']}"
        assert d["messages_out"] == 2, f"got {d['messages_out']}"
        assert len(d["top_talkers"]) == 3  # alice, bob, charlie
        # alice sent 5 in + 1 out = 6 total > bob 2 total > charlie 1 in + 1 out = 2
        assert d["top_talkers"][0][0] == "alice"  # top talker
        assert "room:lobby" in d["per_channel"]

    def test_channel_breakdown(self, populated_ctx):
        d = asyncio.run(self._fetch(populated_ctx))
        lobby = d["per_channel"]["room:lobby"]
        assert lobby["in"] >= 3
        assert lobby["out"] >= 1

    def test_zero_active_connections(self, ctx):
        d = asyncio.run(self._fetch(ctx))
        assert d["active_connections"] == 0


# ---------------------------------------------------------------------------
# 3. WebRTC Monitor — no adapter by default; test fallback
# ---------------------------------------------------------------------------


class TestMonitorWebrtc:
    async def _fetch(self, ctx):
        return await _REGISTRY.partials["monitor_webrtc"](ctx)

    def test_no_adapter(self, ctx):
        """No WebRTC adapter mounted — empty data, no crash."""
        d = asyncio.run(self._fetch(ctx))
        assert d["total_peers"] == 0
        assert d["peers"] == {}
        assert d["ice_states"] == {}

    def test_with_monitor_store_data(self, ctx):
        """Feed data via monitor store directly (adapter fallback)."""
        mon = _get_or_create_monitor(ctx.app)
        mon["webrtc"]["peers"]["peer1"] = {
            "ice_state": "connected",
            "tracks": 3,
            "rtt_ms": 42,
            "bytes_sent": 1000,
            "bytes_received": 500,
            "packets_lost": 2,
        }
        mon["webrtc"]["rooms"] = ["room-a", "room-b"]
        d = asyncio.run(self._fetch(ctx))
        assert d["total_peers"] == 1
        assert d["peers"]["peer1"]["ice_state"] == "connected"
        assert d["rooms"] == ["room-a", "room-b"]
        assert d["total_packets_lost"] == 2

    def test_with_mock_adapter(self, ctx):
        """Simulate a WebRTC adapter on the app with live peer data."""
        mock_pc = MagicMock()
        mock_pc._ice_connection_state = "connected"
        mock_pc._dtls_state = "connected"
        mock_pc._tracks = [1, 2]
        mock_pc._data_channels = {"chat": None}
        mock_pc._rtt = 35
        mock_pc._bytes_sent = 5000
        mock_pc._bytes_received = 3000
        mock_pc._packets_lost = 1

        mock_peer = MagicMock()
        mock_peer.pc = mock_pc

        mock_bridge = MagicMock()
        mock_bridge._peers = {"user-abc": mock_peer}

        mock_adapter = MagicMock()
        mock_adapter.bridge = mock_bridge

        ctx.app._webrtc_adapter = mock_adapter
        d = asyncio.run(self._fetch(ctx))
        assert d["total_peers"] == 1
        p = d["peers"]["user-abc"]
        assert p["ice_state"] == "connected"
        assert p["tracks"] == 2
        assert p["rtt_ms"] == 35


# ---------------------------------------------------------------------------
# 4. gRPC Monitor
# ---------------------------------------------------------------------------


class TestMonitorGRPC:
    async def _fetch(self, ctx):
        return await _REGISTRY.partials["monitor_grpc"](ctx)

    def test_empty(self, ctx):
        d = asyncio.run(self._fetch(ctx))
        assert d["total_services"] == 0
        assert d["total_calls"] == 0

    def test_with_observation_data(self, populated_ctx):
        """Data from observe_grpc_call should appear even without adapter."""
        d = asyncio.run(self._fetch(populated_ctx))
        assert d["total_calls"] == 5, f"got {d['total_calls']}"
        assert d["total_errors"] == 1, f"got {d['total_errors']}"
        assert "helloworld.Greeter" in d["services"]
        assert d["services"]["helloworld.Greeter"]["total_calls"] == 4
        hello = d["services"]["helloworld.Greeter"]["methods"].get("SayHello", {})
        assert hello["calls"] == 3

    def test_with_mock_adapter(self, ctx):
        """Simulate gRPC adapter with service registry."""
        mock_method = MagicMock()
        mock_method.name = "DoSomething"

        mock_svc = MagicMock()
        mock_svc.methods = [mock_method]

        mock_adapter = MagicMock()
        mock_adapter._services = {"myapp.MyService": mock_svc}

        ctx.app._grpc_adapter = mock_adapter
        d = asyncio.run(self._fetch(ctx))
        assert d["total_services"] == 1
        assert "myapp.MyService" in d["services"]

    def test_no_adapter_fallback(self, ctx):
        """Observed call without adapter still shows data."""
        observe_grpc_call(ctx.app, "test.Svc", "Method1", 2.5)
        d = asyncio.run(self._fetch(ctx))
        assert d["total_calls"] == 1


# ---------------------------------------------------------------------------
# 5. Adapter Overview
# ---------------------------------------------------------------------------


class TestAdapterOverview:
    async def _fetch(self, ctx):
        return await _REGISTRY.partials["adapter_overview"](ctx)

    def test_detects_rest(self, ctx):
        d = asyncio.run(self._fetch(ctx))
        rest = d["adapters"].get("rest", {})
        assert rest.get("status") == "mounted"
        assert d["mounted_count"] >= 1

    def test_detects_all_absent(self, ctx):
        """No adapters except REST routes."""
        d = asyncio.run(self._fetch(ctx))
        for proto in ("websocket", "webrtc", "grpc"):
            assert d["adapters"][proto]["status"] == "not detected"

    def test_dynamic_discovery(self, ctx):
        """Custom adapter attribute on app should be found."""
        class _FakeAdapter:
            pass
        _FakeAdapter.__module__ = "rivex_adapter.custom"
        ctx.app.my_custom_adapter = _FakeAdapter()
        d = asyncio.run(self._fetch(ctx))
        assert "my_custom_adapter" in d["adapters"]
        assert d["adapters"]["my_custom_adapter"]["status"] == "mounted"


# ---------------------------------------------------------------------------
# 6. E2E Health Check Action
# ---------------------------------------------------------------------------


async def _run_action(name, ctx):
    return await _REGISTRY.actions[name](ctx)


class TestE2EHealthCheck:
    def test_all_not_mounted(self, ctx):
        d = asyncio.run(_run_action("e2e_health_check", ctx))
        assert d["ok"] is True
        assert d["results"]["rest"]["status"] == "up"
        assert d["results"]["websocket"]["status"] == "not mounted"

    def test_mocked_adapters(self, ctx):
        """Simulate all adapters mounted."""
        ws_adapter = MagicMock()
        ws_adapter.connection_count.return_value = 5
        ctx.app._ws_adapter = ws_adapter

        rtc_adapter = MagicMock()
        rtc_bridge = MagicMock()
        rtc_bridge._peers = {"p1": None, "p2": None}
        rtc_adapter.bridge = rtc_bridge
        ctx.app._webrtc_adapter = rtc_adapter

        grpc_adapter = MagicMock()
        grpc_adapter._services = {"svc1": None}
        ctx.app._grpc_adapter = grpc_adapter

        d = asyncio.run(_run_action("e2e_health_check", ctx))
        assert d["ok"] is True
        assert d["results"]["websocket"]["connections"] == 5
        assert d["results"]["webrtc"]["peers"] == 2

    def test_adapter_error(self, ctx):
        """Adapter that raises should be caught."""
        bad = MagicMock()
        bad.connection_count.side_effect = RuntimeError("boom")
        ctx.app._ws_adapter = bad

        d = asyncio.run(_run_action("e2e_health_check", ctx))
        assert d["ok"] is False
        assert "error" in d["results"]["websocket"]


# ---------------------------------------------------------------------------
# 7. MonitorMiddleware
# ---------------------------------------------------------------------------


class TestMonitorMiddleware:
    def test_middleware_records_requests(self, app):
        mm = MonitorMiddleware(app)
        register_monitor_partials(app)
        mon = _get_or_create_monitor(app)

        async def call_next(req):
            return {"status": 200, "headers": [], "body": b"ok"}

        req = {"method": "GET", "path": "/test", "_app": app}
        asyncio.run(mm.process(req, call_next))

        assert mon["rest"]["counts"].get("GET /test", 0) == 1

    def test_middleware_records_errors(self, app):
        mm = MonitorMiddleware(app)
        register_monitor_partials(app)
        mon = _get_or_create_monitor(app)

        async def call_next(req):
            return {"status": 500, "headers": [], "body": b"error"}

        req = {"method": "POST", "path": "/fail", "_app": app}
        asyncio.run(mm.process(req, call_next))

        assert mon["rest"]["counts"].get("POST /fail", 0) == 1
        assert mon["rest"]["status_codes"].get("500", 0) == 1

    def test_middleware_auto_resolves_app(self, app):
        """Without app= passed, middleware should resolve from request_data."""
        mm = MonitorMiddleware()
        register_monitor_partials(app)
        mon = _get_or_create_monitor(app)

        async def call_next(req):
            return {"status": 200, "headers": [], "body": b"ok"}

        req = {"method": "GET", "path": "/resolve", "_app": app}
        asyncio.run(mm.process(req, call_next))
        assert mon["rest"]["counts"].get("GET /resolve", 0) == 1


# ---------------------------------------------------------------------------
# 8. MonitoredConnectionManager
# ---------------------------------------------------------------------------


class TestMonitoredConnectionManager:
    def test_wraps_and_counts_connections(self, app):
        register_monitor_partials(app)
        mon = _get_or_create_monitor(app)

        class _AsyncMock:
            async def connect(self, ws, rooms=None):
                pass
            def disconnect(self, ws):
                pass

        inner = _AsyncMock()
        mcm = MonitoredConnectionManager(inner, app)

        ws1 = MagicMock()

        async def go():
            await mcm.connect(ws1)
            mcm.disconnect(ws1)

        asyncio.run(go())
        assert mon["websocket"]["active_connections"] == 0
        assert mon["websocket"]["total_connections"] == 1

    def test_counts_messages(self, app):
        register_monitor_partials(app)
        mon = _get_or_create_monitor(app)

        class _AsyncMock:
            async def connect(self, ws, rooms=None):
                pass
            def disconnect(self, ws):
                pass

        inner = _AsyncMock()
        mcm = MonitoredConnectionManager(inner, app)
        ws = MagicMock()

        async def _send_text(text):
            pass
        async def _receive_text():
            return "incoming"
        async def _send_bytes(data):
            pass
        async def _receive_bytes():
            return b"data"
        ws.send_text = _send_text
        ws.receive_text = _receive_text
        ws.send_bytes = _send_bytes
        ws.receive_bytes = _receive_bytes

        async def go():
            await mcm.connect(ws)
            await mcm.send_text(ws, "hello", "room:a")
            await mcm.send_text(ws, "world", "room:a")
            data = await mcm.receive_text(ws, "room:a")
            mcm.disconnect(ws)

        asyncio.run(go())

        assert mon["websocket"]["messages_out"] == 2
        assert mon["websocket"]["messages_in"] == 1
        peer_id = str(id(ws))
        assert mon["websocket"]["per_peer"].get(peer_id, {}).get("total", 0) == 3


# ---------------------------------------------------------------------------
# 9. _sync_from_prometheus bridge
# ---------------------------------------------------------------------------


class TestSyncFromPrometheus:
    def test_seeds_from_metrics_middleware(self, ctx):
        """Simulate MetricsMiddleware counters on the app."""
        from rivex.observability.metrics import Counter, Histogram

        # When the Rust backend is active, Counter/Histogram store data in
        # Rust memory (not in Python _values dicts), so _sync_from_prometheus
        # is a no-op.  We can only test the pure-Python path.
        counter = Counter("http_requests_total", "", labels=["method", "path", "status"])
        if getattr(counter, "_rust", None) is not None:
            pytest.skip("Rust backend active — Prometheus data lives in Rust, not readable from Python")
        counter.inc(method="GET", path="/api/v1/foo", status="200")
        counter.inc(method="GET", path="/api/v1/foo", status="200")
        counter.inc(method="POST", path="/api/v1/foo", status="201")

        hist = Histogram("http_request_duration_seconds", "", labels=["method", "path"])
        hist.observe(0.005, method="GET", path="/api/v1/foo")
        hist.observe(0.010, method="GET", path="/api/v1/foo")

        class FakeRegistry:
            _metrics = [counter, hist]

        ctx.app.metrics = FakeRegistry()

        d = asyncio.run(_REGISTRY.partials["monitor_rest"](ctx))
        assert d["total_requests"] >= 3, f"got {d['total_requests']}"
        assert d["status_breakdown"].get("200", 0) == 2

    def test_no_metrics_middleware(self, ctx):
        """No crash when app has no metrics attribute."""
        d = asyncio.run(_REGISTRY.partials["monitor_rest"](ctx))
        assert d["total_requests"] >= 0  # graceful


# ---------------------------------------------------------------------------
# 10. Edge cases & resilience
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_get_or_create_monitor(self, app):
        """Same app returns same monitor; different apps get different stores."""
        mon1 = _get_or_create_monitor(app)
        mon2 = _get_or_create_monitor(app)
        assert mon1 is mon2

        app2 = Rivex(title="App2")
        mon3 = _get_or_create_monitor(app2)
        assert mon3 is not mon1

    def test_double_registration(self, app):
        """Calling register_monitor_partials twice should not crash."""
        register_monitor_partials(app)
        register_monitor_partials(app)  # second call
        assert hasattr(app, "_monitor_store")

    def test_observe_without_register(self, app):
        """Observation hooks work even without register_monitor_partials."""
        observe_rest_request(app, "GET", "/", 200, 1.0)
        mon = _get_or_create_monitor(app)
        assert mon["rest"]["counts"].get("GET /", 0) == 1

    def test_monitor_middleware_no_app(self):
        """Middleware without app should not crash."""
        mm = MonitorMiddleware()
        async def call_next(req):
            return {"status": 200, "headers": [], "body": b""}
        req = {"method": "GET", "path": "/no-app"}
        result = asyncio.run(mm.process(req, call_next))
        assert result["status"] == 200

    def test_latency_ewma(self, app):
        """Rolling EWMA percentiles should converge."""
        for i in range(100):
            observe_rest_request(app, "GET", "/stable", 200, 10.0)
        mon = _get_or_create_monitor(app)
        lat = mon["rest"]["latencies"]["GET /stable"]
        assert 9.0 <= lat["p50"] <= 11.0

    def test_ws_message_zero_size(self, app):
        """Zero-length messages should not crash."""
        observe_ws_message(app, "p1", "ch", "in", 0)
        mon = _get_or_create_monitor(app)
        assert mon["websocket"]["messages_in"] == 1


# ---------------------------------------------------------------------------
# 11. Built-in admin partials still work
# ---------------------------------------------------------------------------


class TestBuiltinPartialsUnaffected:
    def test_runtime_still_works(self, ctx):
        d = asyncio.run(_REGISTRY.partials["runtime"](ctx))
        assert "requests_served" in d

    def test_overview_still_works(self, ctx):
        d = asyncio.run(_REGISTRY.partials["overview"](ctx))
        assert d["service"] in ("Test", "Rivex")  # "Rivex" is the fallback default


# ---------------------------------------------------------------------------
# 12. register_monitor_partials side-effects
# ---------------------------------------------------------------------------


class TestRegisterMonitorPartials:
    def test_sets_monitor_store(self, app):
        assert not hasattr(app, "_monitor_store")
        register_monitor_partials(app)
        assert hasattr(app, "_monitor_store")

    def test_sets_monitor_started_at(self, app):
        register_monitor_partials(app)
        assert hasattr(app, "_monitor_started_at")
        assert app._monitor_started_at > 0

    def test_wraps_existing_ws_manager(self, app):
        from rivex.protocols.ws import ConnectionManager

        app._ws_manager = ConnectionManager()
        register_monitor_partials(app)
        assert isinstance(app._ws_manager, MonitoredConnectionManager)

    def test_does_not_double_wrap(self, app):
        from rivex.protocols.ws import ConnectionManager

        app._ws_manager = ConnectionManager()
        register_monitor_partials(app)
        register_monitor_partials(app)  # second call
        # Should still be MonitoredConnectionManager, not doubly wrapped
        assert isinstance(app._ws_manager, MonitoredConnectionManager)
        assert not isinstance(app._ws_manager._inner, MonitoredConnectionManager)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
