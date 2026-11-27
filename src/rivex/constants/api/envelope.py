"""``rivex.constants.api.envelope`` — standard API envelope field names + status values."""

from __future__ import annotations

from typing import Final

from rivex.constants.abstraction import IConstant
from rivex.constants.api.abstraction import IAPIConstant


class ApiStatus(IAPIConstant):
    """Coarse-grained ``api_status`` field values returned by every envelope.

    Distinct from :class:`HTTPStatus` (which is the numeric HTTP response
    code) — these are the application-level status strings that clients
    switch on for branching logic.
    """

    OK: Final[str] = "OK"
    SUCCESS: Final[str] = "SUCCESS"
    FAILED: Final[str] = "FAILED"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "ApiStatus"


class ApiResponseKey(IConstant):
    """Stable top-level keys in the standard API response envelope.

    Use these instead of string literals when reading / writing the
    envelope so a typo doesn't silently drop a field on the wire.
    """

    TRANSACTION_URN: Final[str] = "transactionURN"
    STATUS: Final[str] = "status"
    RESPONSE_MESSAGE: Final[str] = "responseMessage"
    RESPONSE_KEY: Final[str] = "responseKey"
    ERRORS: Final[str] = "errors"
    TIMESTAMP: Final[str] = "timestamp"
    METADATA: Final[str] = "metadata"
    DATA: Final[str] = "data"
    REFERENCE_URN: Final[str] = "referenceURN"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "ApiResponseKey"


__all__ = ["ApiStatus", "ApiResponseKey"]
