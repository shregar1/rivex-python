"""``rivex.utilities.response`` — URN minting and ISO timestamp response utilities."""

from __future__ import annotations

import datetime
import secrets
import time

from rivex.utilities.abstraction import IUtility


class ResponseUtility(IUtility):
    """Utility class providing URN generation and ISO-8601 timestamping.

    All methods are static/class methods encapsulated within this utility class.
    """

    @classmethod
    def mint_urn(cls) -> str:
        """Stamp a unique per-request URN (e.g. ``urn:rivex:18b2f9a12c:a4b3c2d1e0f9``)."""
        ms = int(time.time() * 1000)
        return f"urn:rivex:{ms:x}:{secrets.token_hex(6)}"

    @classmethod
    def mint_reference_urn(cls, domain: str, identifier: str) -> str:
        """Stamp a domain-scoped reference URN (e.g. ``urn:rivex:user:usr_12345``)."""
        clean_domain = domain.strip().lower().replace(" ", "_")
        clean_id = identifier.strip()
        return f"urn:rivex:{clean_domain}:{clean_id}"

    @classmethod
    def iso8601_now(cls) -> str:
        """Return the current UTC timestamp formatted as ISO-8601."""
        return datetime.datetime.now(datetime.timezone.utc).isoformat()


__all__ = ["ResponseUtility"]
