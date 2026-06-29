"""Tests for features implemented in Rust with Python wrappers."""

import asyncio
import json
import threading

import rivex_core
from rivex import ASGIAdapter, EventSourceResponse, Rivex, StreamingResponse, TestClient

# ---------------------------------------------------------------------------
# Streaming response tests
# ---------------------------------------------------------------------------


class TestStreamingResponse:
    def test_sync_generator_streaming(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        def gen():
            yield "chunk1"
            yield "chunk2"
            yield "chunk3"

        @app.get("/stream")
        def stream_endpoint():
            return StreamingResponse(gen(), media_type="text/plain")

        client = TestClient(app)
        resp = client.get("/stream")
        assert resp.status_code == 200
        assert resp.text == "chunk1chunk2chunk3"
        assert resp.headers["content-type"] == "text/plain"

    def test_async_generator_streaming(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        async def gen():
            yield "hello "
            yield "world"

        @app.get("/async-stream")
        async def stream_endpoint():
            return StreamingResponse(gen(), media_type="text/plain")

        client = TestClient(app)
        resp = client.get("/async-stream")
        assert resp.status_code == 200
        assert resp.text == "hello world"

    def test_streaming_bytes(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        def gen():
            yield b"\x00\x01"
            yield b"\x02\x03"

        @app.get("/binary-stream")
        def stream():
            return StreamingResponse(gen(), media_type="application/octet-stream")

        client = TestClient(app)
        resp = client.get("/binary-stream")
        assert resp.status_code == 200
        assert resp.content == b"\x00\x01\x02\x03"

    def test_sse_streaming(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        async def gen():
            yield EventSourceResponse.format_event("msg1", event="update")
            yield EventSourceResponse.format_event("msg2", event="update")

        @app.get("/sse")
        def sse():
            return EventSourceResponse(gen())

        client = TestClient(app)
        resp = client.get("/sse")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "event: update" in resp.text
        assert "data: msg1" in resp.text
        assert "data: msg2" in resp.text

    def test_streaming_with_custom_status(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        def gen():
            yield "partial"

        @app.get("/partial")
        def partial():
            return StreamingResponse(gen(), status_code=206, media_type="text/plain")

        client = TestClient(app)
        resp = client.get("/partial")
        assert resp.status_code == 206


# ---------------------------------------------------------------------------
# ASGI adapter tests
# ---------------------------------------------------------------------------


class TestASGIAdapter:
    def _make_app(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        @app.get("/hello")
        def hello():
            return {"message": "world"}

        @app.get("/users/{user_id}")
        def get_user(user_id: int):
            return {"id": user_id}

        @app.post("/echo")
        async def echo(request):
            body = await request.json()
            return body

        return app

    def test_asgi_basic_get(self):
        app = self._make_app()
        adapter = ASGIAdapter(app)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/hello",
            "headers": [],
            "query_string": b"",
        }

        responses = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            responses.append(msg)

        asyncio.run(adapter(scope, receive, send))

        assert len(responses) == 2
        assert responses[0]["type"] == "http.response.start"
        assert responses[0]["status"] == 200
        body = json.loads(responses[1]["body"])
        assert body == {"message": "world"}

    def test_asgi_path_params(self):
        app = self._make_app()
        adapter = ASGIAdapter(app)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/users/42",
            "headers": [],
            "query_string": b"",
        }
        responses = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            responses.append(msg)

        asyncio.run(adapter(scope, receive, send))

        body = json.loads(responses[1]["body"])
        assert body == {"id": 42}

    def test_asgi_not_found(self):
        app = self._make_app()
        adapter = ASGIAdapter(app)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/nonexistent",
            "headers": [],
            "query_string": b"",
        }
        responses = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            responses.append(msg)

        asyncio.run(adapter(scope, receive, send))
        assert responses[0]["status"] == 404

    def test_asgi_method_not_allowed(self):
        app = self._make_app()
        adapter = ASGIAdapter(app)

        scope = {
            "type": "http",
            "method": "DELETE",
            "path": "/hello",
            "headers": [],
            "query_string": b"",
        }
        responses = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            responses.append(msg)

        asyncio.run(adapter(scope, receive, send))
        assert responses[0]["status"] == 405

    def test_asgi_streaming(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        async def gen():
            yield "A"
            yield "B"
            yield "C"

        @app.get("/stream")
        def stream():
            return StreamingResponse(gen(), media_type="text/plain")

        adapter = ASGIAdapter(app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/stream",
            "headers": [],
            "query_string": b"",
        }
        responses = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            responses.append(msg)

        asyncio.run(adapter(scope, receive, send))

        assert responses[0]["type"] == "http.response.start"
        assert responses[0]["status"] == 200
        body_parts = [r["body"] for r in responses[1:] if r.get("body")]
        full_body = b"".join(body_parts)
        assert full_body == b"ABC"

    def test_rivex_call_creates_asgi(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        @app.get("/test")
        def test_endpoint():
            return {"ok": True}

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }
        responses = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            responses.append(msg)

        asyncio.run(app(scope, receive, send))
        assert responses[0]["status"] == 200
        body = json.loads(responses[1]["body"])
        assert body == {"ok": True}


# ---------------------------------------------------------------------------
# SharedState tests (Rust dashmap)
# ---------------------------------------------------------------------------


class TestSharedState:
    def test_set_and_get_str(self):
        state = rivex_core.SharedState()
        state.set_str("name", "rivex")
        assert state.get("name") == "rivex"

    def test_set_and_get_int(self):
        state = rivex_core.SharedState()
        state.set_int("count", 42)
        assert state.get("count") == 42

    def test_set_and_get_float(self):
        state = rivex_core.SharedState()
        state.set_float("pi", 3.14)
        val = state.get("pi")
        assert abs(val - 3.14) < 0.001

    def test_set_and_get_bool(self):
        state = rivex_core.SharedState()
        state.set_bool("active", True)
        assert state.get("active") is True

    def test_set_and_get_bytes(self):
        state = rivex_core.SharedState()
        state.set_bytes("data", b"\x00\x01\x02")
        assert state.get("data") == b"\x00\x01\x02"

    def test_missing_key(self):
        state = rivex_core.SharedState()
        assert state.get("nonexistent") is None

    def test_delete(self):
        state = rivex_core.SharedState()
        state.set_str("key", "value")
        assert state.delete("key") is True
        assert state.get("key") is None
        assert state.delete("key") is False

    def test_contains(self):
        state = rivex_core.SharedState()
        assert state.contains("x") is False
        state.set_int("x", 1)
        assert state.contains("x") is True

    def test_len_and_clear(self):
        state = rivex_core.SharedState()
        assert state.len() == 0
        state.set_str("a", "1")
        state.set_str("b", "2")
        assert state.len() == 2
        state.clear()
        assert state.len() == 0

    def test_increment(self):
        state = rivex_core.SharedState()
        assert state.increment("counter", 1) == 1
        assert state.increment("counter", 1) == 2
        assert state.increment("counter", 5) == 7
        assert state.increment("counter", -3) == 4

    def test_keys(self):
        state = rivex_core.SharedState()
        state.set_str("alpha", "a")
        state.set_int("beta", 2)
        keys = sorted(state.keys())
        assert keys == ["alpha", "beta"]

    def test_concurrent_access(self):
        state = rivex_core.SharedState()
        num_threads = 10
        iterations = 100

        def worker(thread_id):
            for _i in range(iterations):
                state.increment("shared_counter", 1)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert state.get("shared_counter") == num_threads * iterations


# ---------------------------------------------------------------------------
# RateLimitState tests (Rust sliding window)
# ---------------------------------------------------------------------------


class TestRateLimitState:
    def test_basic_rate_limit(self):
        rl = rivex_core.RateLimitState()
        assert rl.check_rate_limit("user1", 3, 60.0) is True
        assert rl.check_rate_limit("user1", 3, 60.0) is True
        assert rl.check_rate_limit("user1", 3, 60.0) is True
        assert rl.check_rate_limit("user1", 3, 60.0) is False

    def test_different_keys_independent(self):
        rl = rivex_core.RateLimitState()
        for _ in range(5):
            rl.check_rate_limit("key1", 5, 60.0)
        assert rl.check_rate_limit("key1", 5, 60.0) is False
        assert rl.check_rate_limit("key2", 5, 60.0) is True

    def test_get_remaining(self):
        rl = rivex_core.RateLimitState()
        assert rl.get_remaining("ip:1.2.3.4", 10, 60.0) == 10
        rl.check_rate_limit("ip:1.2.3.4", 10, 60.0)
        rl.check_rate_limit("ip:1.2.3.4", 10, 60.0)
        assert rl.get_remaining("ip:1.2.3.4", 10, 60.0) == 8

    def test_clear_key(self):
        rl = rivex_core.RateLimitState()
        for _ in range(5):
            rl.check_rate_limit("burst", 5, 60.0)
        assert rl.check_rate_limit("burst", 5, 60.0) is False
        rl.clear_key("burst")
        assert rl.check_rate_limit("burst", 5, 60.0) is True

    def test_clear_all(self):
        rl = rivex_core.RateLimitState()
        rl.check_rate_limit("a", 1, 60.0)
        rl.check_rate_limit("b", 1, 60.0)
        assert rl.check_rate_limit("a", 1, 60.0) is False
        rl.clear_all()
        assert rl.check_rate_limit("a", 1, 60.0) is True

    def test_concurrent_rate_limiting(self):
        rl = rivex_core.RateLimitState()
        allowed_count = 0
        lock = threading.Lock()
        max_requests = 50

        def worker():
            nonlocal allowed_count
            local_allowed = 0
            for _ in range(20):
                if rl.check_rate_limit("shared", max_requests, 60.0):
                    local_allowed += 1
            with lock:
                allowed_count += local_allowed

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert allowed_count == max_requests


# ---------------------------------------------------------------------------
# StreamSender tests (Rust channel)
# ---------------------------------------------------------------------------


class TestStreamSender:
    def test_create_stream(self):
        stream_id = rivex_core.create_stream()
        assert isinstance(stream_id, int)

    def test_create_stream_sender(self):
        stream_id, sender = rivex_core.create_stream_sender()
        assert isinstance(stream_id, int)
        assert not sender.is_closed()
        sender.close()
        assert sender.is_closed()

    def test_sender_send_after_close(self):
        _, sender = rivex_core.create_stream_sender()
        sender.close()
        assert sender.send_chunk(b"data") is False


# ---------------------------------------------------------------------------
# JSON helpers (Rust serde_json)
# ---------------------------------------------------------------------------


class TestJsonHelpers:
    def test_json_serialize(self):
        data = {"key": "value", "count": 42, "nested": {"inner": True}}
        result = rivex_core.json_serialize(data)
        parsed = json.loads(result)
        assert parsed == data

    def test_json_serialize_list(self):
        data = [1, "two", 3.0, None, True]
        result = rivex_core.json_serialize(data)
        parsed = json.loads(result)
        assert parsed == data

    def test_json_deserialize(self):
        data = b'{"hello": "world", "n": 123}'
        result = rivex_core.json_deserialize(data)
        assert result == {"hello": "world", "n": 123}

    def test_json_roundtrip(self):
        original = {"users": [{"id": 1, "active": True}, {"id": 2, "active": False}]}
        serialized = rivex_core.json_serialize(original)
        deserialized = rivex_core.json_deserialize(serialized)
        assert deserialized == original


# ---------------------------------------------------------------------------
# RivexASGI route resolver tests
# ---------------------------------------------------------------------------


class TestRivexSyncApp:
    def test_add_route_and_dispatch(self):
        app = rivex_core.RivexSyncApp()
        app.add_route(
            "GET", "/hello", lambda req: {"status": 200, "headers": [], "body": b'{"msg":"hi"}'}
        )
        req = {
            "method": "GET",
            "path": "/hello",
            "query_string": "",
            "headers": [],
            "body": b"",
            "path_params": {},
        }
        resp = app.dispatch(req)
        assert resp["status"] == 200
        assert resp["body"] == b'{"msg":"hi"}'

    def test_dispatch_path_params(self):
        app = rivex_core.RivexSyncApp()
        app.add_route(
            "GET",
            "/users/{id}",
            lambda req: {"status": 200, "headers": [], "body": req["path_params"]["id"].encode()},
        )
        req = {
            "method": "GET",
            "path": "/users/42",
            "query_string": "",
            "headers": [],
            "body": b"",
            "path_params": {},
        }
        resp = app.dispatch(req)
        assert resp["body"] == b"42"

    def test_dispatch_404(self):
        app = rivex_core.RivexSyncApp()
        app.add_route("GET", "/exists", lambda req: {"status": 200})
        req = {
            "method": "GET",
            "path": "/missing",
            "query_string": "",
            "headers": [],
            "body": b"",
            "path_params": {},
        }
        resp = app.dispatch(req)
        assert resp["status"] == 404

    def test_dispatch_405(self):
        app = rivex_core.RivexSyncApp()
        app.add_route("GET", "/items", lambda req: {"status": 200})
        req = {
            "method": "DELETE",
            "path": "/items",
            "query_string": "",
            "headers": [],
            "body": b"",
            "path_params": {},
        }
        resp = app.dispatch(req)
        assert resp["status"] == 405

    def test_resolve_returns_handler_and_params(self):
        app = rivex_core.RivexSyncApp()

        def handler(req):
            return {"status": 200}

        app.add_route("GET", "/users/{id}", handler)
        result = app.resolve("GET", "/users/5")
        assert result is not None
        resolved_handler, params = result
        assert resolved_handler is handler
        assert params["id"] == "5"

    def test_resolve_not_found(self):
        app = rivex_core.RivexSyncApp()
        app.add_route("GET", "/x", lambda req: None)
        assert app.resolve("GET", "/y") is None

    def test_has_route(self):
        app = rivex_core.RivexSyncApp()
        app.add_route("POST", "/submit", lambda req: None)
        assert app.has_route("POST", "/submit") is True
        assert app.has_route("GET", "/submit") is False

    def test_methods_for_path(self):
        app = rivex_core.RivexSyncApp()
        app.add_route("GET", "/items", lambda req: None)
        app.add_route("POST", "/items", lambda req: None)
        methods = sorted(app.methods_for_path("/items"))
        assert methods == ["GET", "POST"]

    def test_dispatch_async_handler(self):
        app = rivex_core.RivexSyncApp()

        async def handler(req):
            return {"status": 200, "headers": [], "body": b"async"}

        app.add_route("GET", "/async", handler)
        req = {
            "method": "GET",
            "path": "/async",
            "query_string": "",
            "headers": [],
            "body": b"",
            "path_params": {},
        }
        result = app.dispatch(req)
        assert asyncio.iscoroutine(result)
        resp = asyncio.run(result)
        assert resp["body"] == b"async"

    def test_typed_path_conversion(self):
        app = rivex_core.RivexSyncApp()
        app.add_route("GET", "/items/{id:int}", lambda req: {"status": 200})
        assert app.has_route("GET", "/items/42") is True

    def test_path_catchall(self):
        app = rivex_core.RivexSyncApp()
        app.add_route(
            "GET",
            "/files/{filepath:path}",
            lambda req: {
                "status": 200,
                "headers": [],
                "body": req["path_params"]["filepath"].encode(),
            },
        )
        req = {
            "method": "GET",
            "path": "/files/a/b/c.txt",
            "query_string": "",
            "headers": [],
            "body": b"",
            "path_params": {},
        }
        resp = app.dispatch(req)
        assert resp["body"] == b"a/b/c.txt"


class TestSyncTestClient:
    def test_routes_through_rust(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        @app.get("/ping")
        def ping():
            return {"pong": True}

        client = TestClient(app)
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"pong": True}

    def test_path_params_via_rust(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        @app.get("/users/{user_id}")
        def get_user(user_id: int):
            return {"id": user_id}

        client = TestClient(app)
        resp = client.get("/users/7")
        assert resp.status_code == 200
        assert resp.json() == {"id": 7}

    def test_typed_path_validation(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        @app.get("/items/{id:int}")
        def get_item(id: int):
            return {"id": id}

        client = TestClient(app)
        assert client.get("/items/10").status_code == 200
        assert client.get("/items/abc").status_code == 404

    def test_regex_path_validation(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        @app.get("/codes/{code:re:[A-Z]{3}}")
        def get_code(code: str):
            return {"code": code}

        client = TestClient(app)
        assert client.get("/codes/ABC").status_code == 200
        assert client.get("/codes/abc").status_code == 404

    def test_host_routing(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        @app.get("/", host="api.local")
        def api():
            return {"app": "api"}

        @app.get("/", host="admin.local")
        def admin():
            return {"app": "admin"}

        client = TestClient(app)
        assert client.get("/", headers={"host": "api.local"}).json()["app"] == "api"
        assert client.get("/", headers={"host": "admin.local"}).json()["app"] == "admin"

    def test_fallback_handler(self):
        app = Rivex(docs_url=None, redoc_url=None, openapi_url=None, health_url=None)

        @app.get("/real")
        def real():
            return {"ok": True}

        def my_fallback(request):
            return {
                "status": 404,
                "headers": [("content-type", "application/json")],
                "body": b'{"custom":"not found"}',
            }

        app.fallback(my_fallback)
        client = TestClient(app)
        assert client.get("/real").status_code == 200
        resp = client.get("/nope")
        assert resp.json()["custom"] == "not found"


class TestRivexSyncServer:
    def test_create_and_add_routes(self):
        server = rivex_core.RivexSyncServer()
        server.add_route("GET", "/test", lambda req: {"status": 200})
        # Just verify it doesn't crash
        assert server is not None


class TestRustRoutingHelpers:
    def test_match_path_simple(self):
        result = rivex_core.match_path("/users/{id}", "/users/42")
        assert result == {"id": "42"}

    def test_match_path_typed_int(self):
        result = rivex_core.match_path("/items/{id:int}", "/items/7")
        assert result == {"id": 7}

    def test_match_path_typed_float(self):
        result = rivex_core.match_path("/values/{v:float}", "/values/3.14")
        assert result["v"] == 3.14

    def test_match_path_uuid(self):
        result = rivex_core.match_path(
            "/items/{id:uuid}", "/items/550e8400-e29b-41d4-a716-446655440000"
        )
        assert result["id"] == "550e8400-e29b-41d4-a716-446655440000"

    def test_match_path_regex(self):
        result = rivex_core.match_path("/codes/{code:re:[A-Z]{3}}", "/codes/ABC")
        assert result == {"code": "ABC"}

    def test_match_path_regex_no_match(self):
        assert rivex_core.match_path("/codes/{code:re:[A-Z]{3}}", "/codes/abc") is None

    def test_match_path_no_match(self):
        assert rivex_core.match_path("/users/{id}", "/posts/42") is None

    def test_match_path_root(self):
        result = rivex_core.match_path("/", "/")
        assert result == {}

    def test_match_path_catchall(self):
        result = rivex_core.match_path("/files/{fp:path}", "/files/a/b/c.txt")
        assert result == {"fp": "a/b/c.txt"}

    def test_extract_type_constraints(self):
        c = rivex_core.extract_type_constraints("/items/{id:int}/reviews/{rid:uuid}")
        assert c["id"] == ("int", None)
        assert c["rid"] == ("uuid", None)

    def test_extract_type_constraints_regex(self):
        c = rivex_core.extract_type_constraints("/codes/{code:re:[A-Z]{3}}")
        assert c["code"] == ("re", "[A-Z]{3}")

    def test_extract_type_constraints_none(self):
        c = rivex_core.extract_type_constraints("/users/{id}")
        assert c == {}

    def test_validate_path_params_valid(self):
        assert rivex_core.validate_path_params({"id": "42"}, {"id": ("int", None)}) is True

    def test_validate_path_params_invalid(self):
        assert rivex_core.validate_path_params({"id": "abc"}, {"id": ("int", None)}) is False

    def test_validate_path_params_uuid(self):
        assert (
            rivex_core.validate_path_params(
                {"id": "550e8400-e29b-41d4-a716-446655440000"},
                {"id": ("uuid", None)},
            )
            is True
        )
        assert rivex_core.validate_path_params({"id": "not-uuid"}, {"id": ("uuid", None)}) is False

    def test_validate_path_params_regex(self):
        assert (
            rivex_core.validate_path_params({"code": "ABC"}, {"code": ("re", "[A-Z]{3}")}) is True
        )
        assert (
            rivex_core.validate_path_params({"code": "abc"}, {"code": ("re", "[A-Z]{3}")}) is False
        )

    def test_sync_app_host_routing(self):
        app = rivex_core.RivexSyncApp()
        app.add_route(
            "GET", "/", lambda r: {"status": 200, "headers": [], "body": b"api"}, host="api.local"
        )
        app.add_route(
            "GET",
            "/",
            lambda r: {"status": 200, "headers": [], "body": b"admin"},
            host="admin.local",
        )

        r1 = app.resolve("GET", "/", host="api.local")
        assert r1 is not None
        r2 = app.resolve("GET", "/", host="admin.local")
        assert r2 is not None
        assert app.resolve("GET", "/", host="other.local") is None

    def test_sync_app_constraint_validation(self):
        app = rivex_core.RivexSyncApp()
        app.add_route(
            "GET", "/items/{id:int}", lambda r: {"status": 200, "headers": [], "body": b"ok"}
        )

        assert app.has_route("GET", "/items/42") is True
        assert app.has_route("GET", "/items/abc") is False

    def test_sync_app_dispatch_with_constraints(self):
        app = rivex_core.RivexSyncApp()
        app.add_route(
            "GET", "/items/{id:int}", lambda r: {"status": 200, "headers": [], "body": b"ok"}
        )

        req = {"method": "GET", "path": "/items/abc", "headers": [], "body": b"", "path_params": {}}
        resp = app.dispatch(req)
        assert resp["status"] == 404


class TestRivexASGI:
    def test_add_and_resolve_route(self):
        asgi = rivex_core.RivexASGI()

        def handler():
            return "hello"

        asgi.add_route("GET", "/test", handler)
        result = asgi.resolve("GET", "/test")
        assert result is not None
        resolved_handler, params = result
        assert resolved_handler is handler
        assert len(params) == 0

    def test_resolve_with_path_params(self):
        asgi = rivex_core.RivexASGI()

        def handler():
            return "user"

        asgi.add_route("GET", "/users/{id}", handler)
        result = asgi.resolve("GET", "/users/42")
        assert result is not None
        resolved_handler, params = result
        assert resolved_handler is handler
        assert params["id"] == "42"

    def test_resolve_not_found(self):
        asgi = rivex_core.RivexASGI()
        asgi.add_route("GET", "/exists", lambda: None)
        assert asgi.resolve("GET", "/missing") is None

    def test_methods_for_path(self):
        asgi = rivex_core.RivexASGI()
        asgi.add_route("GET", "/items", lambda: None)
        asgi.add_route("POST", "/items", lambda: None)
        methods = sorted(asgi.methods_for_path("/items"))
        assert methods == ["GET", "POST"]

    def test_scope_to_request(self):
        asgi = rivex_core.RivexASGI()
        headers = [("content-type", "application/json")]
        params = {"id": "5"}
        req = asgi.scope_to_request(
            "POST",
            "/api/items",
            b"q=1",
            headers,
            b'{"x":1}',
            params,
            "127.0.0.1",
            8080,
        )
        assert req["method"] == "POST"
        assert req["path"] == "/api/items"
        assert req["query_string"] == "q=1"
        assert req["body"] == b'{"x":1}'
        assert req["client_host"] == "127.0.0.1"
        assert req["client_port"] == 8080
