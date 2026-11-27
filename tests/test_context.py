"""Per-request context (`rivex.context`) tests."""

from __future__ import annotations

import pytest

from rivex.context.context import (
    RequestContext,
    RequestContextMiddleware,
    bind_extra,
    bind_user,
    current_ip,
    current_request_id,
    current_user_agent,
    current_user_id,
    request_context,
)


def _request(method: str = "GET", path: str = "/x", headers=None, remote_addr=None):
    return {
        "method": method,
        "path": path,
        "path_params": {},
        "query_string": "",
        "headers": list(headers or []),
        "body": b"",
        "remote_addr": remote_addr,
    }


@pytest.mark.asyncio
async def test_middleware_populates_context_from_request():
    captured: dict = {}

    async def call_next(req):
        captured["ctx"] = request_context()
        return {"status": 200, "headers": [], "body": b""}

    mw = RequestContextMiddleware()
    await mw.process(
        _request(
            method="POST",
            path="/api/v1/widgets",
            headers=[
                ("user-agent", "MyClient/1.0"),
                ("x-request-id", "req-abc123"),
                ("x-forwarded-for", "203.0.113.42"),
            ],
            remote_addr="10.0.0.1",
        ),
        call_next,
    )
    ctx = captured["ctx"]
    assert ctx.method == "POST"
    assert ctx.path == "/api/v1/widgets"
    assert ctx.user_agent == "MyClient/1.0"
    assert ctx.request_id == "req-abc123"
    assert ctx.ip  # extracted by client_ip; may be x-forwarded-for or remote_addr


@pytest.mark.asyncio
async def test_context_resets_between_requests():
    """The ContextVar must be reset after the request completes."""

    async def call_next(req):
        return {"status": 200, "headers": [], "body": b""}

    mw = RequestContextMiddleware()
    await mw.process(_request(headers=[("user-agent", "first")]), call_next)
    # Outside the request: empty context.
    assert request_context().user_agent is None


def test_request_context_outside_request_is_empty():
    ctx = request_context()
    assert isinstance(ctx, RequestContext)
    assert ctx.user_id is None
    assert ctx.ip is None


@pytest.mark.asyncio
async def test_bind_user_attaches_user_id_to_context():
    captured: dict = {}

    async def call_next(req):
        bind_user("user-42")
        captured["uid"] = current_user_id()
        return {"status": 200, "headers": [], "body": b""}

    mw = RequestContextMiddleware()
    await mw.process(_request(), call_next)
    assert captured["uid"] == "user-42"


@pytest.mark.asyncio
async def test_bind_extra_merges_into_context():
    captured: dict = {}

    async def call_next(req):
        bind_extra(tenant="acme", locale="en-GB")
        captured["ctx"] = request_context()
        return {"status": 200, "headers": [], "body": b""}

    mw = RequestContextMiddleware()
    await mw.process(_request(), call_next)
    assert captured["ctx"].extras == {"tenant": "acme", "locale": "en-GB"}


@pytest.mark.asyncio
async def test_helpers_read_from_current_context():
    captured: dict = {}

    async def call_next(req):
        bind_user(99)
        captured["uid"] = current_user_id()
        captured["ua"] = current_user_agent()
        captured["rid"] = current_request_id()
        captured["ip"] = current_ip()
        return {"status": 200, "headers": [], "body": b""}

    mw = RequestContextMiddleware()
    await mw.process(
        _request(
            headers=[
                ("user-agent", "agent"),
                ("x-request-id", "rid-1"),
                ("x-forwarded-for", "198.51.100.7"),
            ],
            remote_addr="10.0.0.2",
        ),
        call_next,
    )
    assert captured["uid"] == 99
    assert captured["ua"] == "agent"
    assert captured["rid"] == "rid-1"
    assert captured["ip"]


@pytest.mark.asyncio
async def test_concurrent_tasks_have_isolated_contexts():
    """ContextVar must scope per asyncio Task, not leak across them."""
    import asyncio

    seen: list[str | int | None] = []

    async def call_next_a(req):
        bind_user("alice")
        await asyncio.sleep(0)  # yield to the other task
        seen.append(current_user_id())
        return {"status": 200, "headers": [], "body": b""}

    async def call_next_b(req):
        bind_user("bob")
        await asyncio.sleep(0)
        seen.append(current_user_id())
        return {"status": 200, "headers": [], "body": b""}

    mw = RequestContextMiddleware()
    await asyncio.gather(
        mw.process(_request(), call_next_a),
        mw.process(_request(), call_next_b),
    )
    assert set(seen) == {"alice", "bob"}
