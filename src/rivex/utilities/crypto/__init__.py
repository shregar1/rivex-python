"""Crypto utilities package — symmetric and asymmetric helpers unified under ``CryptoUtility``."""

from __future__ import annotations

from typing import Any, Optional

from rivex.utilities.abstraction import LayeredUtility
from rivex.utilities.crypto.abstraction import ICryptoUtility
from rivex.utilities.crypto.asymmetric import AsymmetricCryptoUtility
from rivex.utilities.crypto.payload import PayloadCrypto, PayloadCryptoError
from rivex.utilities.crypto.symmetric import SymmetricCryptoUtility


class CryptoUtility(SymmetricCryptoUtility, AsymmetricCryptoUtility):
    """Unified crypto utility exposing symmetric and asymmetric operations."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "CryptoUtility"


__all__ = [
    "ICryptoUtility",
    "SymmetricCryptoUtility",
    "AsymmetricCryptoUtility",
    "PayloadCrypto",
    "PayloadCryptoError",
    "CryptoUtility",
]
