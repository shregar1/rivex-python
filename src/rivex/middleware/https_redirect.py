"""``rivex.middleware.https_redirect`` — HTTP → HTTPS redirect middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.native._compat import RC_V2, get_request_header, rc as _rc
from rivex.middleware.abstraction import IMiddleware


class HTTPSRedirectMiddleware(IMiddleware):
    """Redirects all plain-HTTP requests to HTTPS with a 307 Temporary Redirect."""

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and upgrade plain-HTTP requests to HTTPS.

        Inspects the ``X-Forwarded-Proto`` header to determine the
        original scheme (falling back to ``"http"``). When the scheme
        is anything other than ``"https"``, builds an absolute HTTPS URL
        for the same host / path / query string (using the Rust helper
        ``build_redirect_url`` when available) and returns a 307
        ``Location`` redirect with an empty body. HTTPS requests are
        forwarded to ``call_next`` unchanged.

        Args:
            request_data: The in-flight request envelope. The
                ``X-Forwarded-Proto`` and ``Host`` headers and the
                ``path`` / ``query_string`` fields are read to build the
                redirect target.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            Either a 307 redirect response when the scheme is not
            ``https``, or the downstream response produced by
            ``call_next``.
        """
        scheme = get_request_header(request_data, Header.X_FORWARDED_PROTO) or "http"
        host = get_request_header(request_data, Header.HOST) or ""

        if scheme.strip() != "https":
            path = request_data.get("path", "/")
            qs = request_data.get("query_string", "")
            if RC_V2:
                url = _rc.build_redirect_url(path, qs, host)
            else:
                url = f"https://{host}{path}"
                if qs:
                    url = f"{url}?{qs}"
            return {"status": HTTPStatus.TEMPORARY_REDIRECT, "headers": [(Header.LOCATION, url)], "body": b""}

        return await call_next(request_data)


__all__ = ["HTTPSRedirectMiddleware"]
