"""``rivex.middleware.max_body_size`` — request body size enforcement middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.http_status import HTTPStatus
from rivex.native._compat import json_error_response
from rivex.middleware.abstraction import IMiddleware


class MaxBodySizeMiddleware(IMiddleware):
    """Rejects requests whose body exceeds a configurable size limit.

    Parameters:
        max_size: Maximum allowed body size in bytes (default 1 MB).
    """

    def __init__(self, max_size: int = 1_048_576):
        self.max_size = max_size

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and reject oversized request bodies.

        Inspects ``request_data["body"]`` when it is ``bytes``. Any body
        longer than :attr:`max_size` short-circuits with a 413
        ``"Request body too large"`` response. Bodies that are ``str``
        (i.e. already decoded) or absent are forwarded to ``call_next``
        without size enforcement.

        Args:
            request_data: The in-flight request envelope. ``body`` is
                read when present.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            Either a 413 payload-too-large response when the body
            exceeds :attr:`max_size`, or the downstream response
            produced by ``call_next``.
        """
        body = request_data.get("body", b"")
        if isinstance(body, bytes) and len(body) > self.max_size:
            return json_error_response(HTTPStatus.PAYLOAD_TOO_LARGE, "Request body too large")
        return await call_next(request_data)


__all__ = ["MaxBodySizeMiddleware"]
