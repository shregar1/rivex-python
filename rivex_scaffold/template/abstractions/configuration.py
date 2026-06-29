"""Configuration contract — singleton, validated, loadable at boot."""

from __future__ import annotations

from abc import ABC, ABCMeta, abstractmethod
from typing import Self

from abstractions.singleton import SingletonMeta


class ABCSingletonMeta(SingletonMeta, ABCMeta):
    """Combines ABC and singleton semantics without metaclass conflict."""


class IConfiguration(ABC, metaclass=ABCSingletonMeta):
    """Root configuration interface. Concrete singletons live in ``configurations/``; env vars in ``configs/``."""

    @classmethod
    @abstractmethod
    def source(cls) -> str:
        """Origin label: ``env``, ``file``, ``vault``, etc."""

    @classmethod
    @abstractmethod
    def layer_name(cls) -> str:
        """Logical layer name for logs and errors."""

    @classmethod
    @abstractmethod
    def load(cls) -> Self:
        """Load, validate, and return the singleton instance."""

    @abstractmethod
    def validate(self) -> None:
        """Fail-fast validation before the server accepts traffic."""

    @classmethod
    def get_instance(cls) -> Self:
        """Return the singleton, loading on first access."""
        if cls not in SingletonMeta._instances:
            return cls.load()
        return SingletonMeta._instances[cls]  # type: ignore[return-value]
