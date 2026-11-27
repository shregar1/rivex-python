"""``rivex.utilities.urn`` — URN, UUID, ULID, and random-string minting utility."""

from __future__ import annotations

import secrets
import string
from typing import Optional
from uuid import UUID, uuid4

try:
    import ulid as _ulid_lib

    _HAS_ULID = True
except ImportError:  # pragma: no cover - ulid is an optional runtime dep
    _ulid_lib = None
    _HAS_ULID = False

from rivex.utilities.abstraction import LayeredUtility


class URNUtility(LayeredUtility):
    """Mint UUIDs, ULIDs, and ``urn:<prefix>:<hex>`` tokens."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    @staticmethod
    def generate_uuid4() -> UUID:
        """Return a fresh RFC-4122 UUID v4."""
        return uuid4()

    @staticmethod
    def generate_uuid() -> str:
        """Return a fresh UUID v4 rendered as ``str``."""
        return str(uuid4())

    @staticmethod
    def generate_ulid() -> str:
        """Return a fresh ULID string. Requires the ``ulid`` package."""
        if not _HAS_ULID:
            raise NotImplementedError(
                "ULID generation requires the optional 'ulid' dependency. "
                "Install it via `pip install ulid-py`."
            )
        return _ulid_lib.new().str

    @staticmethod
    def generate_random_string(length: int) -> str:
        """Return a random ASCII + digit string of ``length`` characters."""
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def generate_urn(self, prefix: str) -> str:
        """Return a ``urn:<prefix>:<hex>`` token using a fresh UUIDv4."""
        return f"urn:{prefix}:{self.generate_uuid4().hex}"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "URNUtility"


__all__ = ["URNUtility"]
