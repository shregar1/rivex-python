"""``rivex.middleware.trusted_host`` — trusted host validation middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.native._compat import RC_V2, get_request_header, json_error_response, rc as _rc
from rivex.middleware.abstraction import IMiddleware


class TrustedHostMiddleware(IMiddleware):
    """Rejects requests whose ``Host`` header is not in the allow-list.

    Parameters:
        allowed_hosts: List of permitted hostnames. ``["*"]`` disables enforcement.
    """

    def __init__(self, allowed_hosts: list[str] | None = None):
        self.allowed_hosts = {h.lower() for h in (allowed_hosts or ["*"])}

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and reject requests with an untrusted ``Host`` header.

        When :attr:`allowed_hosts` contains the wildcard ``"*"`` every
        request is forwarded to ``call_next``. Otherwise the
        ``Host`` header is read (and stripped of any ``:port`` suffix)
        and compared against the configured allow list — preferring the
        Rust core's ``check_trusted_host`` when available. Untrusted
        hosts short-circuit with a 400 ``"Invalid host header"``
        response.

        Args:
            request_data: The in-flight request envelope. The ``Host``
                header is read.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            Either a 400 response when the host is not in the allow
            list, or the downstream response produced by ``call_next``.
        """
        if "*" in self.allowed_hosts:
            return await call_next(request_data)

        host_header = get_request_header(request_data, Header.HOST) or ""

        if RC_V2:
            trusted = _rc.check_trusted_host(host_header, list(self.allowed_hosts))
        else:
            host = host_header.split(":")[0].lower()
            trusted = host in self.allowed_hosts

        if not trusted:
            return json_error_response(HTTPStatus.BAD_REQUEST, "Invalid host header")
        return await call_next(request_data)


__all__ = ["TrustedHostMiddleware"]
