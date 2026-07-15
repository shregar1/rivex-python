from __future__ import annotations

from collections.abc import Callable

from rivex.core._compat import HAS_CORE, get_request_header, json_error_response, parse_request_cookies
from rivex.core._compat import rc as _rc
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
        cookies = parse_request_cookies(request_data)
        return cookies.get(self.cookie_name)

    def _get_header_token(self, request_data: dict) -> str | None:
        return get_request_header(request_data, self.header_name)

    def _tokens_match(self, cookie: str, header: str) -> bool:
        if HAS_CORE:
            result: bool = _rc.hmac_compare(cookie, header)
            return result
        import hmac

        return hmac.compare_digest(cookie, header)

    def _generate_token(self) -> str:
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
        return json_error_response(403, detail)
