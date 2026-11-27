"""``rivex.middleware.timeout`` — async request timeout middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.http_status import HTTPStatus
from rivex.native._compat import json_error_response
from rivex.middleware.abstraction import IMiddleware


class TimeoutMiddleware(IMiddleware):
    """Cancels slow handlers after a configurable timeout.

    Parameters:
        timeout: Maximum seconds to wait for a handler to complete (default 30s).
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and abort the request when it exceeds :attr:`timeout`.

        Wraps ``call_next(request_data)`` in :func:`asyncio.wait_for` with
        the configured :attr:`timeout` (in seconds). On success the
        downstream response is returned unchanged. On
        :class:`asyncio.TimeoutError` a ``504 Gateway Timeout`` JSON
        error response is returned.

        Args:
            request_data: The in-flight request envelope. Forwarded to
                ``call_next`` unchanged.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            Either the downstream response produced by ``call_next``, or
            a 504 timeout error response when :attr:`timeout` elapses
            before the handler completes.
        """
        import asyncio

        try:
            result: dict = await asyncio.wait_for(call_next(request_data), timeout=self.timeout)
            return result
        except asyncio.TimeoutError:
            return json_error_response(HTTPStatus.GATEWAY_TIMEOUT, "Request Timeout")


__all__ = ["TimeoutMiddleware"]
