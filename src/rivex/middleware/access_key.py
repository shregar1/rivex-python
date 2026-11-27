"""``rivex.middleware.access_key`` — enforce per-route ``X-Access-Key`` headers.

Routes registered with ``access_key="..."`` (via ``include_route``,
``@post(access_key=...)``, or the matching :class:`Controller`
class attribute) require the incoming request to carry an
``X-Access-Key`` header with the same value. Mismatches short-circuit
with ``403 Forbidden`` and a stable JSON envelope.

The middleware walks :attr:`Rivex._routes` once at startup to build
a fast ``{ path: access_key }`` lookup, then compares every
incoming request's ``X-Access-Key`` against the route's expected value.
Routes with no ``access_key`` set pass through untouched.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.constants.exception.code import ExceptionCode
from rivex.middleware.abstraction import IMiddleware


class AccessKeyMiddleware(IMiddleware):
    """Reject requests whose ``X-Access-Key`` doesn't match the route's access key.

    Parameters:
        routes: Sequence of ``RouteRecord``-like objects (any object
            with ``.path`` and ``.access_key``). Typically
            ``app._routes`` collected at startup.
        header_name: Override the request header name. Default
            ``"X-Access-Key"``.
        header_value: Reserved for the rare case where the framework
            itself signs every internal request with a known key.
            ``None`` means enforce whatever the route requires.
    """

    DEFAULT_HEADER: str = "x-access-key"

    def __init__(
        self,
        routes: Any,
        *,
        header_name: str = DEFAULT_HEADER,
        header_value: str | None = None,
    ) -> None:
        self._lookup: dict[str, str] = {
            str(r.path): r.access_key
            for r in routes
            if getattr(r, "access_key", None)
        }
        self._header_name = header_name
        self._header_value = header_value

    @staticmethod
    def _read_header(request_data: dict, name: str) -> str | None:
        """Look up a header in ``request_data`` with case-insensitive matching.

        Args:
            request_data: The in-flight request envelope. Its
                ``headers`` list is searched.
            name: Header name to look up; matched case-insensitively.

        Returns:
            The header value as a string when found, otherwise
            ``None``. Non-string keys in the headers list are skipped.
        """
        for key, value in request_data.get("headers") or []:
            if isinstance(key, str) and key.lower() == name.lower():
                return value
        return None

    @staticmethod
    def _reject(reference_urn: Any, message: str) -> dict:
        """Build a standard ``403 Forbidden`` response dict.

        Args:
            reference_urn: The transaction URN copied into the error
                envelope. Typically ``request_data["urn"]``.
            message: Human-readable rejection reason included in the
                envelope.

        Returns:
            A response dict with status 403, an ``application/json``
            content-type header, and a JSON error envelope body.
        """
        envelope = {
            "api_status": "FAILURE",
            "transaction_urn": reference_urn,
            "errors": [
                {
                    "code": ExceptionCode.FORBIDDEN,
                    "message": message,
                }
            ],
        }
        return {
            "status": HTTPStatus.FORBIDDEN,
            "headers": [(Header.CONTENT_TYPE, MediaType.APPLICATION_JSON)],
            "body": json.dumps(envelope).encode("utf-8"),
        }

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Enforce the per-route ``X-Access-Key`` requirement.

        Looks up the request's path in the access-key table built from
        ``routes`` at construction time. When the path is not in the
        table (no access key required), the request is forwarded to
        ``call_next`` immediately. Otherwise the configured
        ``X-Access-Key`` is read — falling back to ``header_value``
        when set on the middleware — and compared to the expected
        value. A missing or mismatched header produces a 403
        :meth:`_reject` response with a stable JSON envelope; a
        matching value forwards the request normally.

        Args:
            request_data: The in-flight request envelope. The ``path``
                and ``headers`` fields are read.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            Either the downstream response produced by ``call_next``,
            or a 403 rejection response when the access key is missing
            or does not match the route's expected value.
        """
        path = request_data.get("path") or ""
        expected = self._lookup.get(path)
        if expected is None:
            return await call_next(request_data)

        provided = self._header_value or self._read_header(request_data, self._header_name)
        if provided is None:
            return self._reject(
                request_data.get("urn"),
                f"Missing {self._header_name} header",
            )
        if provided != expected:
            return self._reject(
                request_data.get("urn"),
                f"Invalid {self._header_name}",
            )

        return await call_next(request_data)


__all__ = ["AccessKeyMiddleware"]
