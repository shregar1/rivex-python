"""``rivex.utilities.hashing`` — password hashing and verification."""

from __future__ import annotations

from typing import Any

from rivex._rust import hash_password, verify_password
from rivex.utilities.abstraction import LayeredUtility


class HashingUtility(LayeredUtility):
    """Password hashing helpers backed by Rivex's Rust core."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    def hash(self, password: str, algorithm: str = "argon2") -> str:
        """Hash ``password`` with the named algorithm and return the encoded hash string.

        Accepts either a plain string (``"argon2"``, ``"bcrypt"``) or
        an enum with a ``.value`` attribute (e.g. ``HashingAlgorithm.ARGON2``).
        """
        alg_str = str(algorithm.value) if hasattr(algorithm, "value") else str(algorithm)
        try:
            return hash_password(password, alg_str)
        except TypeError:
            return hash_password(password)

    def verify(self, password: str, password_hash: str) -> bool:
        """Return ``True`` when ``password`` matches the previously-hashed ``password_hash``."""
        return verify_password(password, password_hash)

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "HashingUtility"


__all__ = ["HashingUtility"]
