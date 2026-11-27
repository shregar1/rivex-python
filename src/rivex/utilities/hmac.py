"""``rivex.utilities.hmac`` — HMAC signing and timing-attack-safe verification."""

from __future__ import annotations

import hashlib
import hmac

from rivex.utilities.abstraction import LayeredUtility


class HMACUtility(LayeredUtility):
    """HMAC signature generation and timing-attack safe verification."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    def generate(self, key: bytes | str, data: bytes | str, algorithm: str = "sha256") -> str:
        """Return the HMAC hex digest for ``data`` keyed by ``key``."""
        k = key.encode() if isinstance(key, str) else key
        d = data.encode() if isinstance(data, str) else data
        digestmod = getattr(hashlib, algorithm.lower(), hashlib.sha256)
        return hmac.new(k, d, digestmod).hexdigest()

    def verify(
        self,
        key: bytes | str,
        data: bytes | str,
        signature: str,
        algorithm: str = "sha256",
    ) -> bool:
        """Verify ``signature`` for ``data`` keyed by ``key`` with a timing-safe comparison."""
        expected = self.generate(key, data, algorithm=algorithm)
        return hmac.compare_digest(expected, signature)

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "HMACUtility"


__all__ = ["HMACUtility"]
