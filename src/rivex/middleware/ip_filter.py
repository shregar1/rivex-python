"""``rivex.middleware.ip_filter`` — IP allow/deny middleware with CIDR support."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.http_status import HTTPStatus
from rivex.native._compat import client_ip, json_error_response
from rivex.middleware.abstraction import IMiddleware


class IPFilterMiddleware(IMiddleware):
    """Allow or deny requests by client IP address. Supports CIDR notation.

    Evaluation order: ``deny`` list is checked first, then ``allow`` list.
    If an ``allow`` list is provided and the IP is not in it, the request is
    rejected. If no lists are provided all traffic passes.

    Parameters:
        allow: List of allowed CIDR ranges (e.g. ``["10.0.0.0/8"]``).
        deny:  List of denied CIDR ranges.
    """

    def __init__(
        self,
        allow: list[str] | None = None,
        deny: list[str] | None = None,
    ):
        import ipaddress

        self._allow = [ipaddress.ip_network(a, strict=False) for a in allow] if allow else []
        self._deny = [ipaddress.ip_network(d, strict=False) for d in deny] if deny else []

    def _is_blocked(self, ip_str: str) -> bool:
        """Return ``True`` when ``ip_str`` should be rejected by this filter.

        Evaluation order: any entry in :attr:`_deny` containing the address
        blocks it; otherwise, when :attr:`_allow` is non-empty, only addresses
        inside one of those networks are allowed. With both lists empty every
        address passes.

        Args:
            ip_str: The client IP address as a string. Parsed as both
                IPv4 and IPv6 — the parser raises ``ValueError`` on bad input.

        Returns:
            ``True`` when the request must be rejected, ``False`` when it
            may pass through.
        """
        import ipaddress

        addr = ipaddress.ip_address(ip_str)
        for net in self._deny:
            if addr in net:
                return True
        if self._allow:
            for net in self._allow:
                if addr in net:
                    return False
            return True
        return False

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Reject the request when the client IP fails the allow/deny check.

        Extracts the client IP via :func:`client_ip` and short-circuits
        with a 403 ``"Forbidden"`` response when :meth:`_is_blocked`
        reports the address is denied (or not in the allow list).
        Otherwise the request is forwarded to ``call_next``.

        Args:
            request_data: The in-flight request envelope. The client IP
                is read via :func:`client_ip`.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            Either a 403 forbidden response when the IP is blocked, or
            the downstream response produced by ``call_next``.
        """
        ip = client_ip(request_data)
        if self._is_blocked(ip):
            return json_error_response(HTTPStatus.FORBIDDEN, "Forbidden")
        return await call_next(request_data)


__all__ = ["IPFilterMiddleware"]
