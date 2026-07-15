"""Tests for the @authenticated / @admin_only decorators."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from rivex.auth.auth import (
    admin_only,
    authenticated,
    current_user,
    set_user_resolver,
)
from rivex.core.context import RequestContextMiddleware, current_user_id, request_context
from rivex.core.exceptions import HTTPException
from rivex.core.requests import Request


@dataclass
class _User:
    id: int
    email: str
    role: str = "user"


def _request(headers=None) -> Request:
    return Request._from_raw(
        {
            "method": "GET",
            "path": "/x",
            "headers": headers or [],
            "body": b"",
            "query_string": "",
            "path_params": {},
        }
    )


# ---------------------------------------------------------------------------
# @authenticated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticated_runs_resolver_and_invokes_handler():
    async def resolver(req: Request) -> _User | None:
        return _User(id=42, email="a@b")

    ran = {}

    @authenticated(resolver=resolver)
    async def handler(request: Request):
        ran["user_id"] = current_user_id()
        ran["user"] = current_user()
        return {"ok": True}

    result = await handler(_request())
    assert result == {"ok": True}
    assert ran["user_id"] == 42
    assert isinstance(ran["user"], _User)
    assert ran["user"].email == "a@b"


@pytest.mark.asyncio
async def test_authenticated_returns_401_when_resolver_returns_none():
    async def resolver(req: Request) -> None:
        return None

    @authenticated(resolver=resolver)
    async def handler(request: Request):
        raise AssertionError("handler must not run")

    with pytest.raises(HTTPException) as exc:
        await handler(_request())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_via_middleware_e2e():
    """End-to-end: with the context middleware installed, an
    unauthenticated request to a decorated handler comes back as 401
    without the handler running."""
    from rivex.core._injection import build_handler_wrapper

    async def resolver(req: Request) -> _User | None:
        return None

    handler_ran = {"yes": False}

    @authenticated(resolver=resolver)
    async def handler(request: Request):
        handler_ran["yes"] = True
        return {"ok": True}

    wrapper = build_handler_wrapper(handler, "/x", 200, False)

    mw = RequestContextMiddleware()

    async def call_next(req):
        return await wrapper(req)

    result = await mw.process(
        {
            "method": "GET",
            "path": "/x",
            "path_params": {},
            "query_string": "",
            "headers": [],
            "body": b"",
        },
        call_next,
    )
    assert result["status"] == 401
    assert handler_ran["yes"] is False


@pytest.mark.asyncio
async def test_authenticated_with_sync_resolver():
    def resolver(req: Request) -> _User:
        return _User(id=1, email="x@y")

    @authenticated(resolver=resolver)
    async def handler(request: Request):
        return {"id": current_user_id()}

    assert (await handler(_request()))["id"] == 1


@pytest.mark.asyncio
async def test_authenticated_inject_passes_user_to_handler():
    async def resolver(req: Request) -> _User:
        return _User(id=7, email="u@v")

    @authenticated(resolver=resolver, inject=True)
    async def handler(request: Request, user: _User = None):
        return {"email": user.email}

    assert (await handler(_request()))["email"] == "u@v"


@pytest.mark.asyncio
async def test_authenticated_uses_default_resolver_when_set():
    async def app_resolver(req: Request) -> _User:
        return _User(id=99, email="app@x")

    set_user_resolver(app_resolver)
    try:

        @authenticated
        async def handler(request: Request):
            return {"id": current_user_id()}

        assert (await handler(_request()))["id"] == 99
    finally:
        # Reset for other tests.
        set_user_resolver(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Role enforcement / @admin_only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_only_forbids_non_admin():
    async def resolver(req: Request) -> _User:
        return _User(id=1, email="x@y", role="user")

    @admin_only(resolver=resolver)
    async def handler(request: Request):
        raise AssertionError("handler must not run")

    with pytest.raises(HTTPException) as exc:
        await handler(_request())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_only_allows_admin():
    async def resolver(req: Request) -> _User:
        return _User(id=1, email="x@y", role="admin")

    @admin_only(resolver=resolver)
    async def handler(request: Request):
        return {"ok": True}

    assert await handler(_request()) == {"ok": True}


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticated_requires_request_param():
    async def resolver(req):
        return _User(id=1, email="x@y")

    @authenticated(resolver=resolver)
    async def handler(other_thing: str):
        return {}

    with pytest.raises(RuntimeError, match="Request"):
        await handler("not a Request")


@pytest.mark.asyncio
async def test_authenticated_without_resolver_raises():
    set_user_resolver(None)  # type: ignore[arg-type]

    @authenticated
    async def handler(request: Request):
        return {}

    with pytest.raises(RuntimeError, match="resolver"):
        await handler(_request())


@pytest.mark.asyncio
async def test_context_extras_user_visible_in_request_body():
    async def resolver(req: Request) -> _User:
        return _User(id=5, email="hi@x", role="admin")

    @authenticated(resolver=resolver)
    async def handler(request: Request):
        ctx = request_context()
        return {"in_extras": isinstance(ctx.extras.get("user"), _User)}

    assert (await handler(_request()))["in_extras"] is True
