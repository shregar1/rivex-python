"""``rivex.middleware.payload_encryption`` — symmetric Fernet payload encryption middleware.

Decrypts incoming request bodies and re-encrypts outgoing response bodies
using a per-user symmetric key. The per-user key lookup is **not**
owned by this middleware — the app provides a :class:`KeyResolver`
callable that returns the raw Fernet key for the given ``user_id`` /
``session_urn`` pair. The middleware owns the rest of the pipeline:

1. Read ``user_id`` and ``session_urn`` from ``request_data["state"]``
   (typically populated by :class:`AuthenticationMiddleware`).
2. Resolve the user's Fernet key through the injected callable.
3. Unprotect the stored value via :class:`PayloadCrypto` (PBKDF2 + AES-GCM).
4. Fernet-decrypt the request body in place.
5. Hand off to the next middleware.
6. Fernet-encrypt the JSON response body on the way back.

The middleware deliberately doesn't know about the user's data store —
swap in a different :class:`KeyResolver` (Redis, secrets manager,
file-based, …) and the same middleware runs unchanged.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any, Optional

from rivex.constants.api.header import Header
from rivex.constants.api.media_type import MediaType
from rivex.constants.context import Context
from rivex.constants.crypto import Encryption
from rivex.middleware.abstraction import IMiddleware
from rivex.utilities.crypto.payload import PayloadCrypto, PayloadCryptoError
from rivex.utilities.request import RequestStateUtility


class KeyResolver(ABC):
    """Pluggable resolver that returns the raw Fernet key for a user.

    The middleware calls :meth:`resolve(user_id, session_urn)` and expects
    a Fernet key string. Return ``None`` when the user has no active
    payload key — the middleware will reject the request as 401.
    """

    @abstractmethod
    def resolve(self, user_id: int, session_urn: Optional[str]) -> Optional[str]:
        """Return the user's raw Fernet key, or ``None`` if none is provisioned."""


class CallbackKeyResolver(KeyResolver):
    """Adapter that turns a plain function into a :class:`KeyResolver`."""

    def __init__(self, fn: Callable[[int, Optional[str]], Optional[str]]) -> None:
        self._fn = fn

    def resolve(self, user_id: int, session_urn: Optional[str]) -> Optional[str]:
        return self._fn(user_id, session_urn)


class PayloadEncryptionMiddleware(IMiddleware):
    """Per-user Fernet request/response body encryption.

    Parameters:
        key_resolver: Returns the raw Fernet key for ``(user_id, session_urn)``.
        system_salt: System-wide salt used to derive the AES key that
            unwraps the stored Fernet key. Typically read from the
            ``KEY_ENCRYPTION_SYSTEM_SALT`` env var by the app.
        pbkdf2_salt: Salt passed to PBKDF2 (default
            ``Encryption.DEFAULT_PBKDF2_SALT``).
        pbkdf2_iterations: PBKDF2 iteration count
            (default ``Encryption.DEFAULT_PBKDF2_ITERATIONS``).
        system_key_len: Derived-key length in bytes
            (default ``Encryption.DEFAULT_SYSTEM_KEY_LEN``).
        excluded_paths: Paths to skip (exact match or ``"*"`` suffix glob).
        state_user_key / state_session_key: Keys used to read
            ``user_id`` / ``session_urn`` from ``request_data["state"]``
            (defaults: ``Context.USER_ID`` / ``Context.SESSION_URN``).
        require_state_user: When ``True`` (default), missing ``user_id``
            in the state bag rejects the request with 401 rather than
            silently passing through.
    """

    DEFAULT_EXCLUDED_PATHS: Sequence[str] = (
        "/health",
        "/healthz",
        "/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
    )

    def __init__(
        self,
        key_resolver: KeyResolver,
        system_salt: str,
        *,
        pbkdf2_salt: bytes | str = Encryption.DEFAULT_PBKDF2_SALT.encode("utf-8"),
        pbkdf2_iterations: int = Encryption.DEFAULT_PBKDF2_ITERATIONS,
        system_key_len: int = Encryption.DEFAULT_SYSTEM_KEY_LEN,
        excluded_paths: Optional[Sequence[str]] = None,
        state_user_key: str = Context.USER_ID,
        state_session_key: str = Context.SESSION_URN,
        require_state_user: bool = True,
    ) -> None:
        if isinstance(key_resolver, KeyResolver):
            self._resolver = key_resolver
        elif callable(key_resolver):
            self._resolver = CallbackKeyResolver(key_resolver)  # type: ignore[arg-type]
        else:
            raise TypeError("key_resolver must be a KeyResolver or callable")

        if isinstance(pbkdf2_salt, str):
            pbkdf2_salt = pbkdf2_salt.encode("utf-8")

        self._crypto = PayloadCrypto(
            system_salt=system_salt,
            pbkdf2_salt=pbkdf2_salt,
            pbkdf2_iterations=pbkdf2_iterations,
            system_key_len=system_key_len,
        )
        self.excluded_paths = set(self.DEFAULT_EXCLUDED_PATHS) | set(excluded_paths or ())
        self.state_user_key = state_user_key
        self.state_session_key = state_session_key
        self.require_state_user = require_state_user

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        path = request_data.get("path") or ""
        if path in self.excluded_paths or self._is_excluded(path):
            return await call_next(request_data)

        user_id = RequestStateUtility.get_request_state(request_data, self.state_user_key)
        if not user_id:
            if not self.require_state_user:
                return await call_next(request_data)
            return self._unauthorized_response(reference_urn=request_data.get("urn"))

        try:
            user_id_int = int(user_id)
        except (TypeError, ValueError):
            return self._unauthorized_response(reference_urn=request_data.get("urn"))

        session_urn = RequestStateUtility.get_request_state(
            request_data, self.state_session_key
        )

        try:
            stored_key = self._resolver.resolve(user_id_int, session_urn)
        except Exception:
            return self._internal_error("Key resolver failed", reference_urn=request_data.get("urn"))
        if not stored_key:
            return self._unauthorized_response(
                reference_urn=request_data.get("urn"),
                message="No payload key provisioned for user",
            )

        try:
            raw_fernet_key = self._crypto.unprotect_fernet_key(stored_key)
        except PayloadCryptoError as exc:
            return self._internal_error(str(exc), reference_urn=request_data.get("urn"))

        if not self._decrypt_request_body(request_data, raw_fernet_key):
            return self._bad_request_response(
                message="Failed to decrypt request payload",
                reference_urn=request_data.get("urn"),
            )

        response = await call_next(request_data)
        self._encrypt_response_body(response, raw_fernet_key)
        return response

    @staticmethod
    def _is_excluded(path: str) -> bool:
        for excluded in PayloadEncryptionMiddleware.DEFAULT_EXCLUDED_PATHS:
            if excluded.endswith("*") and path.startswith(excluded[:-1]):
                return True
        return False

    @staticmethod
    def _decode_body(raw: Any) -> bytes:
        if raw is None:
            return b""
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        if isinstance(raw, str):
            return raw.encode("utf-8")
        return b""

    def _decrypt_request_body(self, request_data: dict, fernet_key: str) -> bool:
        """Decrypt the request body in place. Returns False on parse failure."""
        method = (request_data.get("method") or "").upper()
        if method in {"GET", "HEAD", "OPTIONS", "DELETE"}:
            return True

        raw_bytes = self._decode_body(request_data.get("body"))
        if not raw_bytes:
            return True

        try:
            token = raw_bytes.decode("ascii").strip()
            plaintext = self._crypto.fernet_decrypt(fernet_key, token)
        except Exception:
            return False

        try:
            parsed = json.loads(plaintext.decode("utf-8"))
        except Exception:
            return False

        request_data["body"] = json.dumps(parsed, separators=(",", ":")).encode("utf-8")
        RequestStateUtility.set_request_state(request_data, "payload_decrypted", parsed)
        return True

    def _encrypt_response_body(self, response: dict, fernet_key: str) -> None:
        """Encrypt ``response['body']`` (or ``response['body_json']``) with Fernet."""
        body = response.get("body")
        if body is None or body == b"" or body == "":
            return

        if isinstance(body, (bytes, bytearray)):
            try:
                payload_obj = json.loads(bytes(body).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return
        elif isinstance(body, str):
            try:
                payload_obj = json.loads(body)
            except json.JSONDecodeError:
                return
        else:
            payload_obj = body

        cleartext = json.dumps(payload_obj, separators=(",", ":")).encode("utf-8")
        response["body"] = self._crypto.fernet_encrypt(fernet_key, cleartext)

        headers = [
            (k, v)
            for k, v in (response.get("headers") or [])
            if not (isinstance(k, str) and k.lower() == Header.CONTENT_TYPE.lower())
        ]
        headers.append((Header.CONTENT_TYPE, MediaType.APPLICATION_OCTET_STREAM))
        response["headers"] = headers

    @staticmethod
    def _envelope(code: str, message: str, reference_urn: Any) -> dict:
        return {
            "api_status": "FAILURE",
            "transaction_urn": reference_urn,
            "errors": [{"code": code, "message": message}],
        }

    @classmethod
    def _unauthorized_response(cls, reference_urn: Any, message: str = "Unauthorized") -> dict:
        from rivex.constants.api.http_status import HTTPStatus

        body = json.dumps(cls._envelope("UNAUTHORIZED", message, reference_urn)).encode("utf-8")
        return {
            "status": HTTPStatus.UNAUTHORIZED,
            "headers": [(Header.CONTENT_TYPE, MediaType.APPLICATION_JSON)],
            "body": body,
        }

    @classmethod
    def _bad_request_response(cls, message: str, reference_urn: Any) -> dict:
        from rivex.constants.api.http_status import HTTPStatus

        body = json.dumps(cls._envelope("BAD_REQUEST", message, reference_urn)).encode("utf-8")
        return {
            "status": HTTPStatus.BAD_REQUEST,
            "headers": [(Header.CONTENT_TYPE, MediaType.APPLICATION_JSON)],
            "body": body,
        }

    @classmethod
    def _internal_error(cls, message: str, reference_urn: Any) -> dict:
        from rivex.constants.api.http_status import HTTPStatus

        body = json.dumps(cls._envelope("INTERNAL_ERROR", message, reference_urn)).encode("utf-8")
        return {
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "headers": [(Header.CONTENT_TYPE, MediaType.APPLICATION_JSON)],
            "body": body,
        }


__all__ = ["KeyResolver", "CallbackKeyResolver", "PayloadEncryptionMiddleware"]
