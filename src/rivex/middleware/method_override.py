"""``rivex.middleware.method_override`` — HTTP method override middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.header import Header
from rivex.native._compat import get_request_header
from rivex.middleware.abstraction import IMiddleware


class MethodOverrideMiddleware(IMiddleware):
    """Rewrites the HTTP method using a custom request header.

    Enables HTML forms (which only support GET/POST) to tunnel PUT, PATCH,
    and DELETE via a header like ``X-HTTP-Method-Override``.

    Parameters:
        header_name: Request header that carries the desired method override.
    """

    def __init__(self, header_name: str = Header.X_HTTP_METHOD_OVERRIDE):
        self._header = header_name.lower()

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        override = get_request_header(request_data, self._header)
        if override:
            request_data = dict(request_data)
            request_data["method"] = override.upper()
        return await call_next(request_data)


__all__ = ["MethodOverrideMiddleware"]
