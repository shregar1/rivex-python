from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from rivex.native._compat import HAS_CORE, parse_request_cookies
from rivex.native._compat import rc as _rc
from rivex.middleware.middleware import Middleware


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
        """Run the middleware chain with cookie-based session support.

        Loads the existing session from the request cookies (when valid),
        attaches it as a mutable copy on ``request_data["session"]`` so
        handlers can read and mutate it, then forwards the request to
        ``call_next``. After the downstream response is collected, the
        middleware compares the post-handler session to the pre-handler
        snapshot and, when they differ, signs the new session payload
        and appends a ``Set-Cookie`` header (with the configured path,
        max-age, SameSite, Secure, HTTPOnly, and domain attributes) to
        the response. When the post-handler session is empty but a
        session was loaded originally, an expiry ``Set-Cookie`` is
        emitted so the cookie is cleared in the browser.

        Args:
            request_data: The in-flight request envelope. The session
                cookie is read from here and ``session_data`` is added.
            call_next: Awaitable that invokes the next middleware or
            handler and returns the downstream response dict.

        Returns:
            The downstream response dict, possibly with a ``Set-Cookie``
            header appended for the session payload or expiry.
        """
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
            parts.append("HTTPOnly")
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
        """Extract and verify the session payload from the request cookies.

        Pulls the cookie map off the request envelope, finds the
        configured session cookie, runs :meth:`_verify` on its value,
        and JSON-decodes the resulting bytes. Returns an empty dict
        when the cookie is missing, malformed, fails verification, or
        does not decode as JSON.

        Args:
            request_data: The in-flight request envelope. The cookies
                are read via :func:`parse_request_cookies`.

        Returns:
            The decoded session dict, or an empty dict when no valid
            session could be reconstructed.
    """
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
        """Sign ``data`` and return a base64-and-HMAC token.

        Prefers the Rust core's ``session_sign`` helper when the native
        extension is available. Otherwise falls back to a portable
        ``base64(data).hex-hmac-sha256`` scheme using
        ``self.secret_key``.

        Args:
            data: The session payload bytes to sign.

        Returns:
            A token string combining the encoded payload and signature.
            The exact format depends on whether the Rust core is
            available.
        """
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
        """Verify a session token, returning the original payload bytes.

        Prefers the Rust core's ``session_verify`` when available;
        otherwise performs an HMAC-SHA256 constant-time comparison
        against the trailing signature and base64-decodes the leading
        payload. Returns ``None`` for tokens that lack the ``.``
        separator, are not valid base64, or whose signature does not
        match.

        Args:
            token: The cookie value to verify, in the format produced
                by :meth:`_sign`.

        Returns:
            The original payload bytes when verification succeeds, or
            ``None`` otherwise.
        """
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
