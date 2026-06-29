from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from rivex._compat import HAS_CORE, parse_request_cookies
from rivex._compat import rc as _rc
from rivex.middleware import Middleware


class SessionMiddleware(Middleware):
    """Cookie-based session middleware with signed cookies."""

    def __init__(
        self,
        secret_key: str,
        session_cookie: str = "session",
        max_age: int = 14 * 24 * 3600,
        path: str = "/",
        same_site: str = "lax",
        https_only: bool = False,
        domain: str | None = None,
    ):
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.path = path
        self.same_site = same_site
        self.https_only = https_only
        self.domain = domain

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        session_data = self._load_session(request_data)
        request_data = dict(request_data)
        request_data["session"] = session_data
        original = json.dumps(session_data, sort_keys=True)

        response: dict = await call_next(request_data)

        current = json.dumps(request_data["session"], sort_keys=True)
        if current != original:
            cookie = self._sign(current.encode())
            parts = [f"{self.session_cookie}={cookie}"]
            parts.append(f"Path={self.path}")
            parts.append(f"Max-Age={self.max_age}")
            parts.append(f"SameSite={self.same_site}")
            if self.https_only:
                parts.append("Secure")
            parts.append("HttpOnly")
            if self.domain:
                parts.append(f"Domain={self.domain}")
            if isinstance(response, dict):
                headers = list(response.get("headers", []))
                headers.append(("set-cookie", "; ".join(parts)))
                response["headers"] = headers

        if not request_data["session"] and session_data:
            parts = [f"{self.session_cookie}="]
            parts.append(f"Path={self.path}")
            parts.append("Max-Age=0")
            if isinstance(response, dict):
                headers = list(response.get("headers", []))
                headers.append(("set-cookie", "; ".join(parts)))
                response["headers"] = headers

        return response

    def _load_session(self, request_data: dict) -> dict[str, Any]:
        cookies = parse_request_cookies(request_data)
        token = cookies.get(self.session_cookie)
        if token:
            data = self._verify(token)
            if data is not None:
                try:
                    loaded: dict[str, Any] = json.loads(data)
                    return loaded
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
        return {}

    def _sign(self, data: bytes) -> str:
        if HAS_CORE:
            result: str = _rc.session_sign(data, self.secret_key)
            return result
        import hashlib
        import hmac
        from base64 import b64encode

        encoded = b64encode(data).decode()
        sig = hmac.new(self.secret_key, data, hashlib.sha256).hexdigest()
        return f"{encoded}.{sig}"

    def _verify(self, token: str) -> bytes | None:
        if HAS_CORE:
            result: bytes | None = _rc.session_verify(token, self.secret_key)
            return result
        if "." not in token:
            return None
        import hashlib
        import hmac
        from base64 import b64decode

        encoded, sig = token.rsplit(".", 1)
        try:
            data = b64decode(encoded)
        except Exception:
            return None
        expected = hmac.new(self.secret_key, data, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected):
            return data
        return None
