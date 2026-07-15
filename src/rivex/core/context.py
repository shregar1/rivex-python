"""Per-request context propagated through a :class:`contextvars.ContextVar`.

Services and utilities deep in the call stack — audit loggers, usage
counters, anything that needs "who is doing this, from where" — should
not have to thread ``user_id`` / ``ip`` / ``user_agent`` through every
input dataclass.  Plug the :class:`RequestContextMiddleware` into your
app and call :func:`request_context` (or :func:`current_user_id` /
:func:`current_ip` / :func:`current_user_agent`) anywhere in the
request-handling task to read the current request's metadata.

The middleware sets the request-scoped fields (``method``, ``path``,
``ip``, ``user_agent``, ``request_id``) before the handler runs.  Auth
middleware downstream — or the handler itself — fills in ``user_id`` by
calling :func:`bind_user`.  ``extras`` is a free-form dict for app-
specific tags (tenant id, locale, feature flag bucket, …).

Compatible with :class:`asyncio` — the context is scoped to the
asyncio Task, so concurrent requests can't see each other's context.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass
class RequestContext:
    """Snapshot of per-request metadata available app-wide."""

    method: str | None = None
    path: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    user_id: str | int | None = None
    extras: dict[str, Any] = field(default_factory=dict)


_EMPTY = RequestContext()

_current: contextvars.ContextVar[RequestContext] = contextvars.ContextVar(
    "rivex.request_context", default=_EMPTY
)


def request_context() -> RequestContext:
    """Return the current request's context, or an empty :class:`RequestContext`
    when called outside a request (e.g. from a background task or at
    startup)."""
    return _current.get()


def current_user_id() -> str | int | None:
    return _current.get().user_id


def current_ip() -> str | None:
    return _current.get().ip


def current_user_agent() -> str | None:
    return _current.get().user_agent


def current_request_id() -> str | None:
    return _current.get().request_id


def bind_user(user_id: str | int | None) -> contextvars.Token[RequestContext]:
    """Attach a user id to the current request context.

    Call from your auth middleware (after token validation) or from the
    handler itself.  Returns the :class:`~contextvars.Token` so callers
    can ``reset`` to the previous value if they want manual scoping.
    """
    cur = _current.get()
    return _current.set(replace(cur, user_id=user_id))


def bind_extra(**kwargs: Any) -> contextvars.Token[RequestContext]:
    """Merge arbitrary tags into the current context's ``extras`` dict."""
    cur = _current.get()
    new_extras = {**cur.extras, **kwargs}
    return _current.set(replace(cur, extras=new_extras))


class RequestContextMiddleware:
    """Populate :func:`request_context` from the incoming request envelope.

    Install before any middleware that depends on the context (auth,
    audit, structured logging):

        app.add_middleware(RequestContextMiddleware)

    The middleware sets ``method``, ``path``, ``ip``, ``user_agent``,
    and ``request_id`` (read from the ``X-Request-ID`` header).  Auth
    middleware downstream fills in ``user_id`` by calling
    :func:`bind_user`.
    """

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        from rivex.core._compat import client_ip, get_request_header

        ctx = RequestContext(
            method=request_data.get("method"),
            path=request_data.get("path"),
            ip=client_ip(request_data) or None,
            user_agent=get_request_header(request_data, "user-agent"),
            request_id=get_request_header(request_data, "x-request-id"),
        )
        token = _current.set(ctx)
        try:
            return await call_next(request_data)
        finally:
            _current.reset(token)


__all__ = [
    "RequestContext",
    "RequestContextMiddleware",
    "bind_extra",
    "bind_user",
    "current_ip",
    "current_request_id",
    "current_user_agent",
    "current_user_id",
    "request_context",
]
