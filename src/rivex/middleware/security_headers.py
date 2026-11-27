"""``rivex.middleware.security_headers`` — common security response headers middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.header import Header
from rivex.native._compat import RC_V2, rc as _rc
from rivex.middleware.abstraction import IMiddleware


class SecurityHeadersMiddleware(IMiddleware):
    """Appends common security headers to every response.

    Uses the Rust ``build_security_headers`` fast path when available.

    Parameters:
        hsts:                     Emit ``Strict-Transport-Security``.
        hsts_max_age:             HSTS ``max-age`` in seconds.
        hsts_include_subdomains:  Include ``includeSubDomains`` directive.
        content_type_nosniff:     Emit ``X-Content-Type-Options: nosniff``.
        frame_options:            Value for ``X-Frame-Options`` (e.g. ``"DENY"``); ``None`` omits.
        xss_protection:           Emit ``X-XSS-Protection: 1; mode=block``.
        referrer_policy:          Value for ``Referrer-Policy``.
    """

    def __init__(
        self,
        hsts: bool = True,
        hsts_max_age: int = 31536000,
        hsts_include_subdomains: bool = True,
        content_type_nosniff: bool = True,
        frame_options: str | None = "DENY",
        xss_protection: bool = True,
        referrer_policy: str = "strict-origin-when-cross-origin",
    ):
        if RC_V2 and hasattr(_rc, "build_security_headers"):
            self._headers = list(
                _rc.build_security_headers(
                    hsts,
                    hsts_max_age,
                    hsts_include_subdomains,
                    content_type_nosniff,
                    frame_options,
                    xss_protection,
                    referrer_policy,
                )
            )
        else:
            self._headers: list[tuple[str, str]] = []
            if hsts:
                val = f"max-age={hsts_max_age}"
                if hsts_include_subdomains:
                    val += "; includeSubDomains"
                self._headers.append((Header.STRICT_TRANSPORT_SECURITY, val))
            if content_type_nosniff:
                self._headers.append((Header.X_CONTENT_TYPE_OPTIONS, "nosniff"))
            if frame_options:
                self._headers.append((Header.X_FRAME_OPTIONS, frame_options))
            if xss_protection:
                self._headers.append((Header.X_XSS_PROTECTION, "1; mode=block"))
            if referrer_policy:
                self._headers.append((Header.REFERRER_POLICY, referrer_policy))

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and append the configured security headers.

        Awaits ``call_next`` to obtain the downstream response, then
        extends the response ``headers`` list with every entry the
        middleware was constructed with. Non-dict responses are returned
        untouched.

        Args:
            request_data: The in-flight request envelope. Unused — the
                security headers are response-only.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            The downstream response dict, with the configured
            ``(header_name, value)`` tuples appended to ``headers``.
            Non-dict responses are returned unchanged.
        """
        response: dict = await call_next(request_data)
        if isinstance(response, dict):
            headers = list(response.get("headers", []))
            headers.extend(self._headers)
            response["headers"] = headers
        return response


__all__ = ["SecurityHeadersMiddleware"]
