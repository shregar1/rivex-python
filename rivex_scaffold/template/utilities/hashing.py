"""Password hashing via Rivex Rust hasher (Argon2 / bcrypt)."""

from __future__ import annotations

from typing import Literal

from rivex import hash_argon2, hash_bcrypt
from rivex import hash_password as _rivex_hash_password
from rivex import verify_password as _rivex_verify_password

from abstractions.utility import IUtility


class HashingUtility(IUtility):
    """Hash and verify passwords using ``rivex`` Rust hasher."""

    @classmethod
    def name(cls) -> str:
        return "hashing"

    def hash(
        self,
        password: str,
        *,
        algorithm: Literal["argon2", "bcrypt"] = "argon2",
    ) -> str:
        if algorithm == "bcrypt":
            return hash_bcrypt(password)
        return hash_argon2(password)

    def hash_password(
        self,
        password: str,
        *,
        algorithm: Literal["argon2", "bcrypt"] = "argon2",
    ) -> str:
        return _rivex_hash_password(password, algorithm=algorithm)

    def verify(self, password: str, password_hash: str) -> bool:
        return _rivex_verify_password(password, password_hash)
