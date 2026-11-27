"""HSTS (Strict-Transport-Security) middleware.

Forces browsers to always use HTTPS for the configured ``max-age``,
preventing SSL-stripping attacks (CWE-319). Recommended for any
production app served over HTTPS.

Usage::

    from rivex.middleware.security import HSTSMiddleware

    app.add_middleware(HSTSMiddleware(max_age=31536000, include_subdomains=True, preload=True))

For full HSTS preload list submission, all three directives must be set
and ``max_age`` must be at least 31536000 (1 year).

Reference: RFC 6797 — HTTP Strict Transport Security (HSTS)
"""

from __future__ import annotations

from rivex.middleware.abstraction import IMiddleware


class HSTSMiddleware(IMiddleware):
    """Adds the ``Strict-Transport-Security`` response header.

    Args:
        max_age: Seconds the browser should force HTTPS (default 31536000 = 1 year).
        include_subdomains: Apply to all subdomains (default ``True``).
        preload: Allow inclusion in the browser's HSTS preload list (default ``False``).
            See https://hstspreload.org for submission requirements.
    """

    def __init__(
        self,
        max_age: int = 31536000,
        *,
        include_subdomains: bool = True,
        preload: bool = False,
    ) -> None:
        parts = [f"max-age={max_age}"]
        if include_subdomains:
            parts.append("includeSubDomains")
        if preload:
            parts.append("preload")
        self._header_value = "; ".join(parts)

    async def process(self, request_data: dict, call_next) -> dict:
        """Run the middleware chain and append the HSTS response header.

        Awaits ``call_next`` and tacks ``Strict-Transport-Security`` onto
        the response ``headers`` list using the value built from
        :attr:`_header_value` (which encodes the configured
        ``max-age``, ``includeSubDomains``, and ``preload`` directives).

        Args:
            request_data: The in-flight request envelope. Unused — the
                HSTS header is response-only.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            The downstream response dict with the HSTS header appended.
        """
        response = await call_next(request_data)
        headers = response.get("headers", [])
        headers.append(("strict-transport-security", self._header_value))
        response["headers"] = headers
        return response
