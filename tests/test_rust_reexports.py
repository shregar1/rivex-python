"""Tests for Rust-backed helpers re-exported on the ``rivex`` package."""

from __future__ import annotations

import json


def test_top_level_hash_and_verify():
    from rivex import hash_argon2, hash_password, verify_password

    digest = hash_argon2("secret")
    assert digest.startswith("$argon2")
    assert verify_password("secret", digest)

    bcrypt_digest = hash_password("secret", algorithm="bcrypt")
    assert bcrypt_digest.startswith("$2")
    assert verify_password("secret", bcrypt_digest)


def test_top_level_validators():
    from rivex import validate_email, validate_phone, validate_uuid

    assert validate_email("user@example.com")
    assert not validate_email("not-an-email")
    assert validate_phone("+14155552671")
    assert validate_uuid("550e8400-e29b-41d4-a716-446655440000")


def test_crypto_submodule():
    from rivex.crypto import aes_gcm_encrypt, hmac_sha256, random_token, sha256

    assert len(sha256(b"hello")) == 64
    assert len(random_token(16)) >= 16
    sig = hmac_sha256(b"key", b"message")
    assert isinstance(sig, str) and len(sig) == 64

    key = b"\x00" * 32
    ciphertext = aes_gcm_encrypt(key, b"plaintext")
    assert isinstance(ciphertext, (bytes, bytearray))


def test_jwt_uses_core_expires_in_api():
    from rivex.jwt import decode, encode

    token = encode({"sub": "user-1"}, "secret", expires_in=3600)
    payload = decode(token, "secret")
    assert payload["sub"] == "user-1"
    assert "exp" in payload


def test_jwt_encode_alg_for_multi_algorithm():
    import rivex_core

    payload = json.dumps({"sub": "user-1"})
    token = rivex_core.jwt_encode_alg(payload, "secret", "HS256")
    out = rivex_core.jwt_decode_alg(token, "secret", "HS256", True)
    assert json.loads(out)["sub"] == "user-1"
