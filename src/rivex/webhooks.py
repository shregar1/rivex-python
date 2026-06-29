from __future__ import annotations

import time
from typing import Literal

from rivex._compat import HAS_CORE
from rivex._compat import rc as _rc
from rivex.exceptions import HTTPException
from rivex.requests import Request


class WebhookVerificationError(Exception):
    """Raised when webhook signature verification fails."""


def _hmac_verify(payload: bytes, secret: str, sig_hex: str) -> bool:
    if HAS_CORE:
        # A malformed (non-hex) signature is an invalid signature, not a server
        # error — the Rust verifier raises ValueError on bad hex, so treat that
        # as a non-match rather than letting it surface as a 400.
        try:
            return bool(_rc.hmac_sha256_verify(secret.encode(), payload, sig_hex))
        except ValueError:
            return False
    import hashlib
    import hmac
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_hex)


def _verify_stripe(
    payload: bytes,
    signature: str,
    secret: str,
    tolerance: int,
) -> bool:
    parts: dict[str, str] = {}
    for item in signature.split(","):
        key, _, value = item.strip().partition("=")
        if key and value:
            parts[key] = value

    timestamp_str = parts.get("t")
    sig_hex = parts.get("v1")

    if not timestamp_str or not sig_hex:
        raise WebhookVerificationError("Invalid Stripe signature format: missing t or v1 component")

    try:
        timestamp = int(timestamp_str)
    except ValueError as exc:
        raise WebhookVerificationError(f"Invalid Stripe timestamp: {timestamp_str}") from exc

    if tolerance > 0 and abs(int(time.time()) - timestamp) > tolerance:
        raise WebhookVerificationError("Stripe webhook timestamp outside tolerance window")

    signed_payload = f"{timestamp}.".encode() + payload

    if HAS_CORE:
        if not bool(_rc.hmac_sha256_verify(secret.encode(), signed_payload, sig_hex)):
            raise WebhookVerificationError("Stripe signature mismatch")
    else:
        import hashlib
        import hmac
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig_hex):
            raise WebhookVerificationError("Stripe signature mismatch")

    return True


def _verify_github(payload: bytes, signature: str, secret: str) -> bool:
    prefix = "sha256="
    sig_hex = signature[len(prefix):] if signature.startswith(prefix) else signature
    if not _hmac_verify(payload, secret, sig_hex):
        raise WebhookVerificationError("GitHub signature mismatch")
    return True


def _verify_generic(payload: bytes, signature: str, secret: str) -> bool:
    if not _hmac_verify(payload, secret, signature):
        raise WebhookVerificationError("Signature mismatch")
    return True


def verify_signature(
    payload: bytes,
    signature: str,
    secret: str,
    *,
    provider: Literal["stripe", "github", "generic"] = "generic",
    tolerance: int = 300,
) -> bool:
    if provider == "stripe":
        return _verify_stripe(payload, signature, secret, tolerance)
    if provider == "github":
        return _verify_github(payload, signature, secret)
    return _verify_generic(payload, signature, secret)


_DEFAULT_HEADERS: dict[str, str] = {
    "stripe": "stripe-signature",
    "github": "x-hub-signature-256",
    "generic": "x-signature",
}


class WebhookGuard:
    def __init__(
        self,
        secret: str,
        provider: Literal["stripe", "github", "generic"] = "generic",
        header: str | None = None,
        tolerance: int = 300,
    ):
        self.secret = secret
        self.provider = provider
        self.header = (header or _DEFAULT_HEADERS.get(provider, "x-signature")).lower()
        self.tolerance = tolerance

    def __call__(self, request: Request) -> bool:
        signature = request.header(self.header)

        if signature is None:
            raise HTTPException(
                401,
                detail=f"Missing webhook signature header: {self.header}",
            )

        payload: bytes = request.body
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        try:
            return verify_signature(
                payload,
                signature,
                self.secret,
                provider=self.provider,
                tolerance=self.tolerance,
            )
        except WebhookVerificationError as exc:
            raise HTTPException(401, detail=str(exc)) from exc
