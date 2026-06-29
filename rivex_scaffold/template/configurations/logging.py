"""Logging configuration singleton."""

from __future__ import annotations

from abstractions.configuration import IConfiguration
from configs import Settings, get_settings
from utilities.logger_adapter import LoggingSetupOptions, init_logging


class LoggingConfiguration(IConfiguration):
    """Singleton for logging output and sampling settings."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._log = settings.logging

    @classmethod
    def source(cls) -> str:
        return "env"

    @classmethod
    def layer_name(cls) -> str:
        return "logging"

    @classmethod
    def load(cls) -> "LoggingConfiguration":
        config = cls(get_settings())
        config.validate()
        return config

    def validate(self) -> None:
        if self._log.log_sample_one_in <= 0:
            raise ValueError("LOG_SAMPLE_ONE_IN must be > 0")
        if self._log.log_stdout_format not in {"pretty", "ndjson"}:
            raise ValueError("LOG_STDOUT_FORMAT must be 'pretty' or 'ndjson'")
        if self._log.log_stdout_color not in {"auto", "always", "never"}:
            raise ValueError("LOG_STDOUT_COLOR must be 'auto', 'always', or 'never'")

    def setup_options(self, **overrides: object) -> LoggingSetupOptions:
        """Build runtime logging options from config, with optional boot overrides."""
        return LoggingSetupOptions.from_settings(self.settings).with_overrides(**overrides)

    def setup(self, **overrides: object) -> None:
        """Initialize logx using config defaults plus optional setup arguments."""
        init_logging(self.setup_options(**overrides))
