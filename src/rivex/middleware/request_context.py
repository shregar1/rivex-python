"""``rivex.middleware.request_context`` — default per-request context middleware.

Populates ``request_data["state"]`` with the framework's standard
context keys so downstream middleware, dependencies, and route
handlers can rely on a consistent shape:

* :data:`rivex.constants.Context.URN`            — fresh UUID minted per request
* :data:`rivex.constants.Context.TRANSACTION_URN`— same value, mirrored for compatibility
* :data:`rivex.constants.Context.REFERENCE_URN`  — value supplied by the client
                                                    (``X-Reference-Urn`` →
                                                    ``X-Reference-Id`` →
                                                    ``X-Request-Id``)
* :data:`rivex.constants.Context.USER_AGENT`     — best-effort client user-agent
* :data:`rivex.constants.Context.IP_ADDRESS`     — best-effort client IP

Configure the middleware once during app construction::

    from rivex import Rivex
    from rivex.middleware.request_context import RequestContextMiddleware

    app = Rivex()
    app.add_middleware(RequestContextMiddleware())

When no reference URN header is supplied the middleware short-
circuits with a JSON ``400 Bad Request`` envelope so handlers
never see an under-tagged request.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

from rivex.constants import Context, Header, HTTPStatus, MediaType
from rivex.middleware.middleware import Middleware
from rivex.utilities.request import RequestHeaderUtility, RequestStateUtility


class RequestContextMiddleware(Middleware):
    """Stamp every request with URN / reference / client metadata."""

    def __init__(
        self,
        require_reference: bool = True,
        user_agent_header: str = Header.USER_AGENT,
        reference_headers: tuple[str, ...] = (
            Header.X_REFERENCE_URN,
            Header.X_REFERENCE_ID,
            Header.X_REQUEST_ID,
        ),
        extra_state: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self.urn = None
        self.tenant_id = None
        self.tenant_urn = None
        self.user_id = None
        self.user_urn = None
        self.api_name = None
        self.ip_address = None
        self.user_agent = None
        self.require_reference = require_reference
        self.user_agent_header = user_agent_header
        self.reference_headers = reference_headers
        self.extra_state = dict(extra_state or {})
    async def process(self, request_data: dict[str, Any], call_next: Callable) -> dict[str, Any]:
        urn_value = str(uuid.uuid4())
        RequestStateUtility.set_request_state(request_data, Context.URN, urn_value)
        RequestStateUtility.set_request_state(request_data, Context.TRANSACTION_URN, urn_value)

        reference_urn = self._read_reference_urn(request_data)
        if self.require_reference and not reference_urn:
            return self._bad_reference_response(urn_value)

        if reference_urn:
            RequestStateUtility.set_request_state(
                request_data, Context.REFERENCE_URN, reference_urn
            )

        user_agent = (
            RequestHeaderUtility.get_request_header(request_data, self.user_agent_header)
            or request_data.get("client_user_agent")
        )
        if user_agent:
            RequestStateUtility.set_request_state(request_data, Context.USER_AGENT, user_agent)

        ip_address = request_data.get("client_ip") or request_data.get("ip_address")
        if ip_address:
            RequestStateUtility.set_request_state(request_data, Context.IP_ADDRESS, ip_address)

        for key, value in self.extra_state.items():
            RequestStateUtility.set_request_state(request_data, key, value)

        return await call_next(request_data)

    @staticmethod
    def _read_reference_urn(request_data: dict[str, Any]) -> str | None:
        for header_name in (
            Header.X_REFERENCE_URN,
            Header.X_REFERENCE_ID,
            Header.X_REQUEST_ID,
        ):
            value = RequestHeaderUtility.get_request_header(request_data, header_name)
            if value:
                return value
        return None

    @staticmethod
    def _bad_reference_response(transaction_urn: str) -> dict[str, Any]:
        envelope = {
            "api_status": "FAILURE",
            "transaction_urn": transaction_urn,
            "errors": [
                {
                    "code": "MISSING_REFERENCE_URN",
                    "message": (
                        "x-reference-urn, x-reference-id, or x-request-id header is required"
                    ),
                }
            ],
        }
        body = json.dumps(envelope).encode("utf-8")
        return {
            "status": HTTPStatus.BAD_REQUEST,
            "headers": [(Header.CONTENT_TYPE, MediaType.APPLICATION_JSON)],
            "body": body,
        }


__all__ = ["RequestContextMiddleware"]
