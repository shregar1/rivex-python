"""Authentication configuration singleton."""

from __future__ import annotations

from abstractions.configuration import IConfiguration
from configs import Settings, get_settings


class AuthConfiguration(IConfiguration):
    """Singleton for JWT token settings."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._auth = settings.auth

    @classmethod
    def source(cls) -> str:
        return "env"

    @classmethod
    def layer_name(cls) -> str:
        return "auth"

    @classmethod
    def load(cls) -> "AuthConfiguration":
        config = cls(get_settings())
        config.validate()
        return config

    def validate(self) -> None:
        if len(self._auth.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if len(self._auth.jwt_refresh_secret) < 32:
            raise ValueError("JWT_REFRESH_SECRET must be at least 32 characters")
