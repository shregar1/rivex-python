"""Rust-accelerated cryptography (SHA, HMAC, AES-GCM, secure random, Ed25519).

Requires the ``rivex-core`` extension. Import via ``from rivex.crypto import sha256``
or use symbols re-exported on the top-level ``rivex`` package where applicable.
"""

from __future__ import annotations

import rivex_core as _rc

sha256 = _rc.sha256
sha512 = _rc.sha512
sha256_bytes = _rc.sha256_bytes
sha512_bytes = _rc.sha512_bytes
hmac_sha256 = _rc.hmac_sha256
hmac_sha512 = _rc.hmac_sha512
hmac_sha256_bytes = _rc.hmac_sha256_bytes
hmac_sha512_bytes = _rc.hmac_sha512_bytes
hmac_sha256_verify = _rc.hmac_sha256_verify
hmac_sha512_verify = _rc.hmac_sha512_verify


def aes_gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    return bytes(_rc.aes_gcm_encrypt(key, plaintext))


def aes_gcm_decrypt(key: bytes, ciphertext: bytes) -> bytes:
    return bytes(_rc.aes_gcm_decrypt(key, ciphertext))


pbkdf2_derive = _rc.pbkdf2_derive
pbkdf2_verify = _rc.pbkdf2_verify
random_bytes = _rc.random_bytes
random_token = _rc.random_token
random_hex = _rc.random_hex
ed25519_keygen = _rc.ed25519_keygen
ed25519_sign = _rc.ed25519_sign
ed25519_verify = _rc.ed25519_verify

__all__ = [
    "sha256",
    "sha512",
    "sha256_bytes",
    "sha512_bytes",
    "hmac_sha256",
    "hmac_sha512",
    "hmac_sha256_bytes",
    "hmac_sha512_bytes",
    "hmac_sha256_verify",
    "hmac_sha512_verify",
    "aes_gcm_encrypt",
    "aes_gcm_decrypt",
    "pbkdf2_derive",
    "pbkdf2_verify",
    "random_bytes",
    "random_token",
    "random_hex",
    "ed25519_keygen",
    "ed25519_sign",
    "ed25519_verify",
]
