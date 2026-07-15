"""Inject a request id and a service-name header so downstream layers can correlate logs."""

from __future__ import annotations

import uuid
from typing import Any

from rivex.core._compat import RC_V2, get_request_header
from rivex.middleware.middleware import Middleware

from configs import PROJECT_NAME, PROJECT_VERSION

try:
    from rivex import rivex_core as _rc
except ImportError:
    _rc = None

SERVICE_NAME_HEADER = "x-service-name"
SERVICE_VERSION_HEADER = "x-service-version"


def _set_request_header(request_data: dict[str, Any], name: str, value: str) -> None:
    headers = list(request_data.get("headers", []))
    lowered = name.lower()
    headers = [(key, val) for key, val in headers if key.lower() != lowered]
    headers.append((name, value))
    request_data["headers"] = headers


class RequestIdMiddleware(Middleware):
    """Ensure every request carries an ``x-request-id`` and identify the service in responses."""

    def __init__(
        self,
        header_name: str = "x-request-id",
        service_name: str = PROJECT_NAME,
        service_version: str = PROJECT_VERSION,
    ) -> None:
        self.header_name = header_name
        self.service_name = service_name
        self.service_version = service_version

    async def process(self, request_data: dict[str, Any], call_next) -> dict[str, Any]:
        incoming_id = get_request_header(request_data, self.header_name)
        if incoming_id:
            request_id = incoming_id
        elif RC_V2 and _rc is not None:
            request_id = _rc.generate_request_id()
        else:
            request_id = uuid.uuid4().hex

        _set_request_header(request_data, self.header_name, request_id)
        response: dict[str, Any] = await call_next(request_data)
        response["headers"] = response.get("headers", []) + [
            (self.header_name, request_id),
            (SERVICE_NAME_HEADER, self.service_name),
            (SERVICE_VERSION_HEADER, self.service_version),
        ]
        return response
