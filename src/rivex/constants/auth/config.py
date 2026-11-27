"""``rivex.constants.auth.config`` — authentication policy + token-format constants."""

from __future__ import annotations

from typing import Final, FrozenSet

from rivex.constants.auth.abstraction import IAuthConstant


class AuthConfigConstant(IAuthConstant):
    """Auth policy constants: password rules, OTP settings, JWT claim names, scope strings."""

    OTP_LENGTH: Final[int] = 6
    OTP_EXPIRY_MINUTES: Final[int] = 10
    MAX_LOGIN_ATTEMPTS: Final[int] = 5

    PASSWORD_MIN_LENGTH: Final[int] = 12
    PASSWORD_MAX_LENGTH: Final[int] = 255

    COMMON_PASSWORDS: Final[FrozenSet[str]] = frozenset(
        {
            "000000000000",
            "111111111111",
            "123456789012",
            "1234567890ab",
            "abc123456789",
            "iloveyou1234",
            "letmein12345",
            "password1234",
            "qwerty123456",
            "qwertyuiopas",
            "welcome12345",
        }
    )

    DEFAULT_SCHEME: Final[str] = "bearer"

    SUBJECT_CLAIM: Final[str] = "sub"
    TENANT_CLAIM: Final[str] = "tenant_urn"
    USER_TYPE_CLAIM: Final[str] = "user_type_urn"
    SESSION_CLAIM: Final[str] = "session_urn"
    USER_CLAIMS_KEY: Final[str] = "user_claims"
    SCOPES_CLAIM: Final[str] = "scopes"

    PUBLIC_REGISTER_USER_TYPES: Final[FrozenSet[str]] = frozenset(
        {"CANDIDATE", "RECRUITER", "COMPANY", "INTERVIEWER"}
    )

    EMPLOYER_INVITE_PATH_TEMPLATE: Final[str] = "/invite/employer/{code}"

    SCOPE_MESSAGING_WRITE: Final[str] = "messaging:write"
    SCOPE_NOTIFICATION_WRITE: Final[str] = "notification:write"
    SCOPE_WEBHOOK_WRITE: Final[str] = "webhook:write"
    SCOPE_ADMIN_ALL: Final[str] = "admin:*"


__all__ = ["AuthConfigConstant"]
