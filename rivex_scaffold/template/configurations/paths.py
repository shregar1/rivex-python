"""Paths configuration singleton."""

from __future__ import annotations

from pathlib import Path

from abstractions.configuration import IConfiguration
from configs import LOGS_DIR, MEDIA_DIR, MEDIA_URL_PREFIX, MIGRATIONS_DIR, SCRIPTS_DIR


class PathsConfiguration(IConfiguration):
    """Singleton for filesystem path defaults from JSON config."""

    def __init__(self) -> None:
        self.logs_dir = LOGS_DIR
        self.migrations_dir = MIGRATIONS_DIR
        self.scripts_dir = SCRIPTS_DIR
        self.media_dir = MEDIA_DIR
        self.media_url_prefix = MEDIA_URL_PREFIX

    @classmethod
    def source(cls) -> str:
        return "file"

    @classmethod
    def layer_name(cls) -> str:
        return "paths"

    @classmethod
    def load(cls) -> "PathsConfiguration":
        config = cls()
        config.validate()
        return config

    def validate(self) -> None:
        if not str(self.logs_dir).strip():
            raise ValueError("paths.logs_dir must not be empty")
        if not str(self.migrations_dir).strip():
            raise ValueError("paths.migrations_dir must not be empty")
        if not str(self.scripts_dir).strip():
            raise ValueError("paths.scripts_dir must not be empty")
        if not str(self.media_dir).strip():
            raise ValueError("paths.media_dir must not be empty")
        if not self.media_url_prefix.startswith("/"):
            raise ValueError("paths.media_url_prefix must start with /")

    def ensure_dirs(self) -> None:
        for d in (self.logs_dir, self.migrations_dir, self.scripts_dir, self.media_dir):
            Path(d).mkdir(parents=True, exist_ok=True)
