"""JWT access and refresh tokens via Rivex Rust-backed JWT."""

from __future__ import annotations

import time
import uuid
from typing import Any

from rivex.jwt import (
    ExpiredTokenError,
    InvalidTokenError,
    JWTError,
)
from rivex.jwt import decode as jwt_decode
from rivex.jwt import encode as jwt_encode

from abstractions.utility import IUtility
from configs import Settings
from configurations import AppConfiguration


class JwtUtility(IUtility):
    """Create and verify JSON Web Tokens."""

    @classmethod
    def name(cls) -> str:
        return "jwt"

    def __init__(self, *, settings: Settings | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._settings = settings or AppConfiguration.load().settings
        self._auth = self._settings.auth

    def create_access_token(self, subject: str, **claims: Any) -> str:
        expires_at = int(time.time()) + self._auth.access_ttl_seconds
        payload = {"sub": subject, "type": "access", "exp": expires_at, **claims}
        return jwt_encode(payload, self._auth.jwt_secret)

    def create_refresh_token(self, subject: str, **claims: Any) -> str:
        expires_at = int(time.time()) + self._auth.refresh_ttl_seconds
        payload = {
            "sub": subject,
            "type": "refresh",
            "exp": expires_at,
            "jti": str(uuid.uuid4()),
            **claims,
        }
        return jwt_encode(payload, self._auth.jwt_refresh_secret)

    def decode_access_token(self, token: str) -> dict[str, Any]:
        return jwt_decode(token, self._auth.jwt_secret)

    def decode_refresh_token(self, token: str) -> dict[str, Any]:
        return jwt_decode(token, self._auth.jwt_refresh_secret)


__all__ = [
    "JwtUtility",
    "JWTError",
    "ExpiredTokenError",
    "InvalidTokenError",
]
