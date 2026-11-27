"""Shared utilities for the SDK."""
from __future__ import annotations

import asyncio
from typing import Any, Callable


def apply_middleware_chain(
    handler: Callable,
    middleware: list[tuple[type, dict[str, Any]]],
) -> Callable:
    """Wrap ``handler`` in the given list of middleware.

    Mirrors the historical ``_apply_middleware`` implementations on
    ``Rivex`` and ``ASGIAdapter`` — kept here so both call sites
    share one definition and the behaviour can't drift.

    Args:
        handler: The base async request handler to wrap.
        middleware: A list of ``(MiddlewareClass, kwargs_dict)``
            tuples, applied in reverse order so the first item in
            the list becomes the OUTERMOST wrapper (matching the
            prior behaviour of iterating ``reversed(middleware)``).
    """
    wrapped = handler
    for middleware_cls, kwargs in reversed(middleware):
        mw = middleware_cls(**kwargs)
        inner = wrapped

        async def make_handler(
            request_data: dict,
            *,
            _mw: Any = mw,
            _next: Callable = inner,
        ) -> dict:
            """Run a single middleware instance and forward the result.

            Dispatches to the middleware's ``process`` coroutine when
            present (catching the case where the middleware only exposes
            a plain callable). Awaits the result transparently so both
            sync and async middlewares integrate seamlessly.

            Args:
                request_data: The in-flight request envelope. The
                    closing ``*`` captures ``_mw`` (the middleware
                    instance) and ``_next`` (the inner handler) per
                    closure iteration.
                _mw: The middleware instance to invoke.
                _next: The wrapped handler / next middleware to call.

            Returns:
                The middleware's response dict (sync or async result
                resolved transparently).
            """
            process = getattr(_mw, "process", None)
            if callable(process):
                result = process(request_data, _next)
            else:
                result = _mw(request_data, _next)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        wrapped = make_handler
    return wrapped
