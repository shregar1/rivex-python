"""``rivex.utilities.jwt`` — JWT access / refresh token helpers."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from rivex.constants.jwt import JWT
from rivex.utilities.abstraction import LayeredUtility
from rivex.utilities.urn import URNUtility


class JWTUtility(LayeredUtility):
    """Sign and verify JWT access / refresh tokens via the Rivex Rust core.

    ``algorithm`` defaults to ``HS256``; pass ``RS256`` (or any other
    algorithm your ``jwt_encode`` / ``jwt_decode`` bindings support)
    through the constructor or per-call.
    """

    def __init__(
        self,
        secret: str,
        refresh_secret: Optional[str] = None,
        algorithm: str = JWT.HS256,
        access_ttl_seconds: int = 900,
        refresh_ttl_seconds: int = 2_592_000,
        urn_utility: Optional[URNUtility] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.secret = secret
        self.refresh_secret = refresh_secret or secret
        self.algorithm = algorithm
        self.access_ttl_seconds = int(access_ttl_seconds)
        self.refresh_ttl_seconds = int(refresh_ttl_seconds)
        self.urn_utility = urn_utility or URNUtility()

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "JWTUtility"

    def _create_payload(
        self,
        subject: str,
        expires_at: int,
        token_type: str,
        jti: str,
        **claims: Any,
    ) -> Dict[str, Any]:
        """Build a signed JWT claim set."""
        return {
            "sub": subject,
            "type": token_type,
            "exp": expires_at,
            "jti": jti,
            **claims,
        }

    def _encode(self, payload: Dict[str, Any], secret: str) -> str:
        """Encode ``payload`` via the Rust core ``jwt_encode_alg`` binding."""
        import json

        import rivex_core

        return rivex_core.jwt_encode_alg(json.dumps(payload, default=str), secret, self.algorithm)

    def _decode(self, token: str, secret: str) -> Dict[str, Any]:
        """Decode ``token`` via the Rust core ``jwt_decode_alg`` binding."""
        import json

        import rivex_core

        return json.loads(rivex_core.jwt_decode_alg(token, secret, self.algorithm))

    def create_access_token(self, subject: str, **claims: Any) -> str:
        """Return a freshly-signed access token with a ``type=access`` claim."""
        expires_at = int(time.time()) + self.access_ttl_seconds
        payload = self._create_payload(
            subject=subject,
            expires_at=expires_at,
            token_type=JWT.ACCESS,
            jti=self.urn_utility.generate_uuid(),
            **claims,
        )
        return self._encode(payload, self.secret)

    def create_refresh_token(self, subject: str, **claims: Any) -> str:
        """Return a freshly-signed refresh token with a ``type=refresh`` claim."""
        expires_at = int(time.time()) + self.refresh_ttl_seconds
        payload = self._create_payload(
            subject=subject,
            expires_at=expires_at,
            token_type=JWT.REFRESH,
            jti=self.urn_utility.generate_uuid(),
            **claims,
        )
        return self._encode(payload, self.refresh_secret)

    def decode_access_token(self, token: str) -> Dict[str, Any]:
        """Decode and verify an access token against the configured access secret."""
        return self._decode(token, self.secret)

    def decode_refresh_token(self, token: str) -> Dict[str, Any]:
        """Decode and verify a refresh token against the configured refresh secret."""
        return self._decode(token, self.refresh_secret)


__all__ = ["JWTUtility"]
