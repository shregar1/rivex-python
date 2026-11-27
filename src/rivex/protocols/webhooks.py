from __future__ import annotations

import time
from typing import Literal

from rivex.native._compat import HAS_CORE
from rivex.native._compat import rc as _rc
from rivex.exceptions.http.exceptions import HTTPException
from rivex.http.requests import Request


class WebhookVerificationError(Exception):
    """Raised when webhook signature verification fails."""


def _hmac_verify(payload: bytes, secret: str, sig_hex: str) -> bool:
    """Verify a hex HMAC-SHA-256 signature in constant time.

    Prefers the Rust ``rivex_core`` verifier when available — a
    malformed (non-hex) signature is treated as a mismatch, not a
    server error, so callers can keep their own 4xx response path
    simple. Falls back to ``hmac.compare_digest`` over a standard
    ``hashlib.sha256`` digest in pure Python.

    Args:
        payload: Raw request body bytes that were signed.
        secret: Shared secret used to compute the HMAC.
        sig_hex: Hex-encoded HMAC supplied by the webhook sender.

    Returns:
        ``True`` when the signature matches, otherwise ``False``.
    """
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
    """Verify a Stripe-style ``Stripe-Signature`` header.

    Parses the ``t=...,v1=...`` style header, enforces the optional
    timestamp tolerance, and HMAC-verifies
    ``f"{timestamp}.".encode() + payload`` using the shared secret.
    Uses the Rust verifier when available and the pure-Python fallback
    otherwise.

    Args:
        payload: Raw request body bytes that were signed.
        signature: The value of the ``Stripe-Signature`` header.
        secret: Webhook signing secret configured in the Stripe
            dashboard.
        tolerance: Maximum number of seconds the timestamp may drift
            from the current time. ``0`` disables the check.

    Returns:
        ``True`` on a valid signature inside the tolerance window.

    Raises:
        WebhookVerificationError: When the header is missing the
            ``t`` or ``v1`` component, when the timestamp is not an
            integer, when the timestamp is outside ``tolerance``, or
            when the HMAC does not match.
    """
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
    """Verify a GitHub-style ``X-Hub-Signature-256`` header.

    Strips the leading ``sha256=`` prefix (if present) and delegates
    the constant-time comparison to :func:`_hmac_verify`.

    Args:
        payload: Raw request body bytes that were signed.
        signature: The value of the ``X-Hub-Signature-256`` header.
        secret: Webhook secret configured in the GitHub repository
            settings.

    Returns:
        ``True`` on a valid signature.

    Raises:
        WebhookVerificationError: When the HMAC does not match.
    """
    prefix = "sha256="
    sig_hex = signature[len(prefix):] if signature.startswith(prefix) else signature
    if not _hmac_verify(payload, secret, sig_hex):
        raise WebhookVerificationError("GitHub signature mismatch")
    return True


def _verify_generic(payload: bytes, signature: str, secret: str) -> bool:
    """Verify a raw hex HMAC-SHA-256 signature with no provider framing.

    Used for the ``"generic"`` provider and as the catch-all fallback
    for unknown ``provider`` values.

    Args:
        payload: Raw request body bytes that were signed.
        signature: Hex-encoded HMAC supplied by the sender.
        secret: Shared secret used to compute the HMAC.

    Returns:
        ``True`` on a valid signature.

    Raises:
        WebhookVerificationError: When the HMAC does not match.
    """
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
    """Verify a webhook signature for the requested provider.

    Dispatches to :func:`_verify_stripe`, :func:`_verify_github` or
    :func:`_verify_generic` based on ``provider``. Stripe and GitHub
    return ``True`` on success and raise
    :class:`WebhookVerificationError` on failure; the generic provider
    follows the same convention.

    Args:
        payload: Raw request body bytes that were signed.
        signature: The header value supplied by the sender (already
            extracted by the caller).
        secret: Shared webhook secret.
        provider: One of ``"stripe"``, ``"github"`` or ``"generic"``.
            Unknown values fall through to the generic verifier.
        tolerance: Maximum number of seconds the timestamp may drift
            from the current time. Only honored for Stripe; ignored
            for other providers. ``0`` disables the check.

    Returns:
        ``True`` on a valid signature.

    Raises:
        WebhookVerificationError: When the signature does not match or
            a provider-specific check (timestamp tolerance, header
            shape) fails.
    """
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
