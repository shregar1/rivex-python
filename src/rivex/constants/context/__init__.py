"""``rivex.constants.context`` — request-state key constants.

State keys stored in ``request_data["state"]`` should be referenced
by these constants (rather than as bare strings) so that middleware
and route handlers stay in sync.  Add new entries here as the
framework grows; never reach into the state dict with a magic
string elsewhere.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.context.abstraction import IContextConstant


class Context(IContextConstant):
    """Standard keys used by framework + middleware when writing to ``request_data["state"]``."""

    URN: Final[str] = "urn"
    TRANSACTION_URN: Final[str] = "transaction_urn"
    REFERENCE_URN: Final[str] = "reference_urn"

    USER_ID: Final[str] = "user_id"
    USER_URN: Final[str] = "user_urn"
    USER_TYPE_URN: Final[str] = "user_type_urn"
    USER_TYPE_CODE: Final[str] = "user_type_code"
    USER_AGENT: Final[str] = "user_agent"

    TENANT_ID: Final[str] = "tenant_id"
    TENANT_URN: Final[str] = "tenant_urn"

    SESSION_URN: Final[str] = "session_urn"
    SESSION_ID: Final[str] = "session_id"

    API_NAME: Final[str] = "api_name"
    IP_ADDRESS: Final[str] = "ip_address"

    AUTHENTICATED: Final[str] = "authenticated"
    AUTHORIZATION_SCOPE: Final[str] = "authorization_scope"

    PROPAGATE: Final[bool] = False


__all__ = ["Context"]
