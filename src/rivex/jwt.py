from __future__ import annotations

import json
from typing import Any

from rivex._compat import HAS_CORE
from rivex._compat import rc as _rc
from rivex.exceptions import HTTPException
from rivex.requests import Request


class JWTError(Exception):
    """Base exception for JWT errors."""


class ExpiredTokenError(JWTError):
    """Token has expired."""


class InvalidTokenError(JWTError):
    """Token is malformed or signature is invalid."""


# ---------------------------------------------------------------------------
# Encode / Decode — delegates to Rust (rivex_core)
# ---------------------------------------------------------------------------


def encode(
    payload: dict[str, Any],
    secret: str,
    algorithm: str = "HS256",
    expires_in: int | None = None,
) -> str:
    if algorithm != "HS256":
        raise JWTError(f"Unsupported algorithm: {algorithm}")

    if HAS_CORE:
        if expires_in is not None and expires_in < 0:
            import time

            payload = dict(payload)
            payload["exp"] = int(time.time()) + expires_in
            expires_in = None
        payload_json = json.dumps(payload, separators=(",", ":"))
        try:
            result: str = _rc.jwt_encode(payload_json, secret, expires_in)
            return result
        except ValueError as e:
            raise InvalidTokenError(str(e)) from e

    import base64
    import hashlib
    import hmac
    import time

    header = {"alg": "HS256", "typ": "JWT"}
    if expires_in is not None:
        payload = dict(payload)
        payload["exp"] = int(time.time()) + expires_in

    def _b64(data: str) -> str:
        return base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()

    def _b64b(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    segs = [
        _b64(json.dumps(header, separators=(",", ":"))),
        _b64(json.dumps(payload, separators=(",", ":"))),
    ]
    si = ".".join(segs)
    sig = hmac.new(secret.encode(), si.encode(), hashlib.sha256).digest()
    segs.append(_b64b(sig))
    return ".".join(segs)


def decode(
    token: str,
    secret: str,
    *,
    verify: bool = True,
) -> dict[str, Any]:
    if HAS_CORE:
        try:
            payload_str: str = _rc.jwt_decode(token, secret, verify)
            decoded: dict[str, Any] = json.loads(payload_str)
            return decoded
        except ValueError as e:
            msg = str(e)
            if msg == "expired":
                raise ExpiredTokenError("Token has expired") from e
            raise InvalidTokenError(msg) from e

    import base64
    import hashlib
    import hmac
    import time

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Token must have exactly three segments")
    header_segment, payload_segment, signature_segment = parts
    if verify:
        si = f"{header_segment}.{payload_segment}"
        expected = hmac.new(secret.encode(), si.encode(), hashlib.sha256).digest()
        padded = signature_segment + "=" * (-len(signature_segment) % 4)
        actual = base64.urlsafe_b64decode(padded)
        if not hmac.compare_digest(expected, actual):
            raise InvalidTokenError("Signature verification failed")
    try:
        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        payload_out: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidTokenError(f"Invalid payload: {exc}") from exc
    if verify and "exp" in payload_out:
        if int(payload_out["exp"]) < int(time.time()):
            raise ExpiredTokenError("Token has expired")
    return payload_out


# ---------------------------------------------------------------------------
# JWTBearer dependency
# ---------------------------------------------------------------------------


class JWTBearer:
    """Dependency that extracts and verifies a JWT from the
    ``Authorization: Bearer <token>`` header.

    Usage with Rivex dependency injection::

        jwt_bearer = JWTBearer(secret="my-secret")

        @app.get("/protected")
        def protected(payload: dict = Depends(jwt_bearer)):
            return {"user": payload["sub"]}
    """

    def __init__(self, secret: str, auto_error: bool = True):
        self.secret = secret
        self.auto_error = auto_error

    def __call__(self, request: Request) -> dict | None:
        authorization = request.header("authorization")

        if not authorization:
            if self.auto_error:
                raise HTTPException(
                    401,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() != "bearer" or not credentials:
            if self.auto_error:
                raise HTTPException(
                    401,
                    detail="Invalid authorization header",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

        try:
            return decode(credentials, self.secret)
        except ExpiredTokenError:
            if self.auto_error:
                raise HTTPException(
                    401,
                    detail="Token has expired",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from None
            return None
        except JWTError:
            if self.auto_error:
                raise HTTPException(
                    401,
                    detail="Invalid token",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from None
            return None
