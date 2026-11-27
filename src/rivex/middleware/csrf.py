from __future__ import annotations

from collections.abc import Callable

from rivex.native._compat import HAS_CORE, get_request_header, json_error_response, parse_request_cookies
from rivex.native._compat import rc as _rc
from rivex.middleware.middleware import Middleware


class CSRFMiddleware(Middleware):
    """Double-submit cookie CSRF protection."""

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

    def __init__(
        self,
        secret_key: str,
        cookie_name: str = "csrftoken",
        header_name: str = "x-csrftoken",
        cookie_path: str = "/",
        cookie_secure: bool = False,
        cookie_same_site: str = "lax",
        exempt_paths: list[str] | None = None,
    ):
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.cookie_path = cookie_path
        self.cookie_secure = cookie_secure
        self.cookie_same_site = cookie_same_site
        self.exempt_paths = set(exempt_paths or [])

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and enforce CSRF on unsafe methods.

        On safe methods (or exempt paths), the request is passed
        through with no checks. On every other mutating request, the
        CSRF cookie token and the configured request header token are
        both required and must match via :meth:`_tokens_match`; any
        missing or mismatched pair short-circuits with a 403 via
        :meth:`_forbidden`. After the downstream response is collected,
        a ``Set-Cookie`` carrying a fresh CSRF token is appended when
        the request did not already present one — that way the browser
        has a token to echo back on the next mutating request.

        Args:
            request_data: The in-flight request envelope. The
                ``method``, ``path``, and ``headers``/cookies are read.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            Either a 403 forbidden response when the CSRF check fails,
            or the downstream response possibly with a ``Set-Cookie``
            appended.
        """
        method = request_data.get("method", "GET").upper()
        path = request_data.get("path", "/")

        cookie_token = self._get_cookie_token(request_data)

        if method not in self.SAFE_METHODS and path not in self.exempt_paths:
            header_token = self._get_header_token(request_data)
            if not cookie_token or not header_token:
                return self._forbidden("CSRF token missing")
            if not self._tokens_match(cookie_token, header_token):
                return self._forbidden("CSRF token mismatch")

        response: dict = await call_next(request_data)

        if not cookie_token:
            token = self._generate_token()
            parts = [f"{self.cookie_name}={token}"]
            parts.append(f"Path={self.cookie_path}")
            parts.append(f"SameSite={self.cookie_same_site}")
            if self.cookie_secure:
                parts.append("Secure")
            if isinstance(response, dict):
                headers = list(response.get("headers", []))
                headers.append(("set-cookie", "; ".join(parts)))
                response["headers"] = headers

        return response

    def _get_cookie_token(self, request_data: dict) -> str | None:
        """Read the configured CSRF cookie from the request envelope.

        Args:
            request_data: The in-flight request envelope. Its cookies
                are parsed via :func:`parse_request_cookies`.

        Returns:
            The CSRF cookie value as a string, or ``None`` when the
            cookie is absent.
        """
        cookies = parse_request_cookies(request_data)
        return cookies.get(self.cookie_name)

    def _get_header_token(self, request_data: dict) -> str | None:
        """Read the configured CSRF header from the request envelope.

        Args:
            request_data: The in-flight request envelope. The header is
                read via :func:`get_request_header` (case-insensitive).

        Returns:
            The CSRF header value as a string, or ``None`` when the
            header is absent.
        """
        return get_request_header(request_data, self.header_name)

    def _tokens_match(self, cookie: str, header: str) -> bool:
        """Compare two tokens in constant time.

        Prefers the Rust core's ``hmac_compare`` when available, falling
        back to :func:`hmac.compare_digest` from the standard library.
        Either implementation resists timing attacks.

        Args:
            cookie: The token read from the cookie.
            header: The token read from the request header.

        Returns:
            ``True`` when both tokens are byte-equal, ``False``
            otherwise.
        """
        if HAS_CORE:
            result: bool = _rc.hmac_compare(cookie, header)
            return result
        import hmac

        return hmac.compare_digest(cookie, header)

    def _generate_token(self) -> str:
        """Generate a fresh CSRF token.

        Prefers the Rust core's ``csrf_generate_token`` when available;
        otherwise falls back to 32 random bytes from
        :func:`secrets.token_bytes` HMAC-SHA256'd with
        ``self.secret_key`` and hex-encoded.

        Returns:
            A new opaque token string suitable for both the cookie
            value and the expected header value.
        """
        if HAS_CORE:
            result: str = _rc.csrf_generate_token(self.secret_key)
            return result
        import hashlib
        import hmac
        import secrets

        raw = secrets.token_bytes(32)
        return hmac.new(self.secret_key, raw, hashlib.sha256).hexdigest()

    @staticmethod
    def _forbidden(detail: str) -> dict:
        """Build a 403 CSRF-rejected response via the standard error helper.

        Args:
            detail: Human-readable reason included in the error body.

        Returns:
            A 403 response dict produced by
            :func:`json_error_response`.
        """
        return json_error_response(403, detail)
