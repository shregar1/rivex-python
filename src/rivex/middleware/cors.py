"""``rivex.middleware.cors`` — Cross-Origin Resource Sharing (CORS) middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.header import Header
from rivex.constants.api.http_method import HTTPMethod
from rivex.constants.api.http_status import HTTPStatus
from rivex.native._compat import (
    RC_V2,
    get_request_header,
    rc as _rc,
)
from rivex.middleware.abstraction import IMiddleware

_CORS_SAFE_METHODS = (
    HTTPMethod.GET,
    HTTPMethod.POST,
    HTTPMethod.PUT,
    HTTPMethod.DELETE,
    HTTPMethod.PATCH,
    HTTPMethod.OPTIONS,
    HTTPMethod.HEAD,
)


class CORSMiddleware(IMiddleware):
    """Handles CORS preflight and appends Access-Control headers to every response.

    Parameters:
        allow_origins:      List of allowed origins; ``["*"]`` permits all.
        allow_methods:      Allowed HTTP methods.
        allow_headers:      Allowed request headers.
        allow_credentials:  Whether ``Access-Control-Allow-Credentials: true`` is emitted.
        max_age:            Preflight cache duration in seconds.
    """

    def __init__(
        self,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        allow_credentials: bool = False,
        max_age: int = 600,
    ):
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or [
            HTTPMethod.GET,
            HTTPMethod.POST,
            HTTPMethod.PUT,
            HTTPMethod.DELETE,
            HTTPMethod.PATCH,
            HTTPMethod.OPTIONS,
        ]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
        self.max_age = max_age

        if self.allow_credentials and ("*" in self.allow_methods or "*" in self.allow_headers):
            import warnings

            offenders = []
            if "*" in self.allow_methods:
                offenders.append("allow_methods")
            if "*" in self.allow_headers:
                offenders.append("allow_headers")
            warnings.warn(
                "CORSMiddleware: allow_credentials=True is incompatible with "
                f"wildcard {' / '.join(offenders)} per the CORS spec — "
                "browsers reject the preflight response.  Rivex will expand "
                "'*' from the request at runtime, but you should enumerate "
                "the methods/headers your API needs (e.g. "
                "allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'], "
                "allow_headers=['content-type','authorization']).",
                stacklevel=2,
            )

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Handle CORS preflight and decorate downstream responses.

        On ``OPTIONS`` requests the middleware short-circuits with a
        ``204 No Content`` preflight response whose headers come from
        :meth:`_cors_headers` (with the requested method / headers
        echoed back when present). All other methods are forwarded to
        ``call_next``; the resulting headers list is extended with the
        same CORS headers so the actual response carries
        ``Access-Control-*`` entries too.

        Args:
            request_data: The in-flight request envelope. The
                ``method`` and ``headers`` fields are read to detect a
                preflight request and to capture the incoming
                ``Origin``/``Access-Control-Request-*`` values.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            A 204 preflight response for ``OPTIONS`` requests, or the
            downstream response dict with CORS headers merged into its
            ``headers`` list.
        """
        origin = get_request_header(request_data, Header.ORIGIN)
        if request_data.get("method") == HTTPMethod.OPTIONS:
            requested_method = get_request_header(request_data, Header.ACCESS_CONTROL_REQUEST_METHOD)
            requested_headers = get_request_header(request_data, Header.ACCESS_CONTROL_REQUEST_HEADERS)
            return {
                "status": HTTPStatus.NO_CONTENT,
                "headers": self._cors_headers(
                    origin,
                    requested_method=requested_method,
                    requested_headers=requested_headers,
                ),
                "body": b"",
            }

        response: dict = await call_next(request_data)
        response["headers"] = response.get("headers", []) + self._cors_headers(origin)
        return response

    def _cors_headers(
        self,
        request_origin: str | None = None,
        *,
        requested_method: str | None = None,
        requested_headers: str | None = None,
    ) -> list[tuple[str, str]]:
        """Build the ``Access-Control-*`` header list for this middleware.

        When the Rust core is available, delegates to ``build_cors_headers``
        which produces the same output with all CORS rules applied.
        Otherwise, expands the configured ``allow_origins``,
        ``allow_methods``, and ``allow_headers`` (with the requested
        method / headers promoted when ``allow_credentials=True`` to
        avoid the wildcard-incompatible-with-credentials pitfall) and
        assembles the standard set of ``Access-Control-Allow-*``
        headers plus ``Vary: Origin`` when the origin allow-list is
        not a wildcard.

        Args:
            request_origin: Origin from the incoming request, if any.
            requested_method: Value of the
                ``Access-Control-Request-Method`` preflight header, when
                present.
            requested_headers: Value of the
                ``Access-Control-Request-Headers`` preflight header, when
                present.

        Returns:
            A list of ``(header_name, header_value)`` tuples. May be
            empty when the origin is not allowed.
    """
        allow_methods = self.allow_methods
        allow_headers = self.allow_headers
        if self.allow_credentials:
            if "*" in allow_methods:
                allow_methods = [requested_method] if requested_method else list(_CORS_SAFE_METHODS)
            if "*" in allow_headers:
                if requested_headers:
                    allow_headers = [h.strip() for h in requested_headers.split(",") if h.strip()]
                else:
                    allow_headers = [Header.CONTENT_TYPE, Header.AUTHORIZATION, Header.ACCEPT]

        if RC_V2:
            return list(
                _rc.build_cors_headers(
                    request_origin or "",
                    self.allow_origins,
                    allow_methods,
                    allow_headers,
                    [],
                    self.allow_credentials,
                    self.max_age,
                    True,
                )
            )
        if "*" in self.allow_origins:
            if self.allow_credentials:
                if not request_origin:
                    return []
                allowed_origin = request_origin
            else:
                allowed_origin = "*"
        elif request_origin and request_origin in self.allow_origins:
            allowed_origin = request_origin
        else:
            return []

        headers: list[tuple[str, str]] = [
            (Header.ACCESS_CONTROL_ALLOW_ORIGIN, allowed_origin),
            (Header.ACCESS_CONTROL_ALLOW_METHODS, ", ".join(allow_methods)),
            (Header.ACCESS_CONTROL_ALLOW_HEADERS, ", ".join(allow_headers)),
            (Header.ACCESS_CONTROL_MAX_AGE, str(self.max_age)),
        ]
        if self.allow_credentials:
            headers.append((Header.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"))
        if "*" not in self.allow_origins:
            headers.append((Header.VARY, "Origin"))
        return headers


__all__ = ["CORSMiddleware"]
