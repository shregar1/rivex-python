"""``rivex.utilities`` — Framework utility layer."""

from __future__ import annotations

from rivex.utilities.abstraction import IUtility, LayeredUtility
from rivex.utilities.crypto import (
    AsymmetricCryptoUtility,
    CryptoUtility,
    ICryptoUtility,
    PayloadCrypto,
    PayloadCryptoError,
    SymmetricCryptoUtility,
)
from rivex.utilities.database import (
    IDatabaseUtility,
    MongoDatabaseUtility,
    PostgresDatabaseUtility,
)
from rivex.utilities.env import EnvUtility
from rivex.utilities.hashing import HashingUtility
from rivex.utilities.hmac import HMACUtility
from rivex.utilities.jwt import JWTUtility
from rivex.utilities.otp import (
    AlphabeticOTPUtility,
    AlphanumericOTPUtility,
    DigitOTPUtility,
    HexOTPUtility,
    IOTPUtility,
    PassphraseOTPUtility,
)
from rivex.utilities.regex import RegexUtility
from rivex.utilities.request import (
    RequestBodyUtility,
    RequestFormUtility,
    RequestHeaderUtility,
    RequestParamUtility,
    RequestStateUtility,
)
from rivex.utilities.response import (
    ResponseBodyUtility,
    ResponseCookieUtility,
    ResponseHeaderUtility,
    ResponseStateUtility,
    ResponseUtility,
)
from rivex.utilities.timing import TimingUtility
from rivex.utilities.urn import URNUtility
from rivex.utilities.validation import ValidationError, ValidationUtility
from rivex.utilities.webhook import WebhookUtility

__all__ = [
    # Base
    "IUtility",
    "LayeredUtility",
    # Existing
    "TimingUtility",
    "ResponseUtility",
    # Request
    "RequestBodyUtility",
    "RequestFormUtility",
    "RequestHeaderUtility",
    "RequestParamUtility",
    "RequestStateUtility",
    # Response
    "ResponseBodyUtility",
    "ResponseCookieUtility",
    "ResponseHeaderUtility",
    "ResponseStateUtility",
    # Crypto
    "ICryptoUtility",
    "SymmetricCryptoUtility",
    "AsymmetricCryptoUtility",
    "PayloadCrypto",
    "PayloadCryptoError",
    "CryptoUtility",
    # Database
    "IDatabaseUtility",
    "MongoDatabaseUtility",
    "PostgresDatabaseUtility",
    # OTP
    "IOTPUtility",
    "DigitOTPUtility",
    "AlphabeticOTPUtility",
    "AlphanumericOTPUtility",
    "HexOTPUtility",
    "PassphraseOTPUtility",
    # Standalone utilities
    "URNUtility",
    "RegexUtility",
    "HMACUtility",
    "HashingUtility",
    "JWTUtility",
    "EnvUtility",
    "ValidationUtility",
    "ValidationError",
    "WebhookUtility",
]
