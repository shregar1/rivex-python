"""``rivex.middleware.request_id`` — request ID propagation middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.header import Header
from rivex.native._compat import RC_V2, get_request_header, rc as _rc
from rivex.middleware.abstraction import IMiddleware


class RequestIdMiddleware(IMiddleware):
    """Stamps every response with a unique ``x-request-id`` header.

    Preserves an incoming ID if the client already supplied one; otherwise
    generates a fresh UUID (or delegates to the Rust core if available).

    Parameters:
        header_name: Header to read from the request and write to the response.
                     Defaults to ``Header.X_REQUEST_ID``.
    """

    def __init__(self, header_name: str = Header.X_REQUEST_ID):
        self.header_name = header_name

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and stamp the response with a request id.

        Reuses an incoming request id when the client already supplied
        one; otherwise generates a fresh id via the Rust core's
        ``generate_request_id`` when available, or ``uuid.uuid4().hex``
        as a stdlib fallback. The resolved id is appended to the
        downstream response ``headers`` list (without overwriting an
        existing entry for the same header).

        Args:
            request_data: The in-flight request envelope. The configured
                header (default ``X-Request-Id``) is read for an
                incoming id.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            The downstream response dict, with the request-id header
            appended.
        """
        incoming_id = get_request_header(request_data, self.header_name)

        if incoming_id:
            request_id = incoming_id
        elif RC_V2:
            request_id = _rc.generate_request_id()
        else:
            import uuid
            request_id = uuid.uuid4().hex

        response: dict = await call_next(request_data)
        response["headers"] = response.get("headers", []) + [(self.header_name, request_id)]
        return response


__all__ = ["RequestIdMiddleware"]
