"""``rivex.utilities.database.abstraction`` — base class for database utilities."""

from __future__ import annotations

from abc import abstractmethod

from rivex.utilities.abstraction import IUtility


class IDatabaseUtility(IUtility):
    """Base class for database utility layers."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Returns the class name."""
        raise NotImplementedError


__all__ = ["IDatabaseUtility"]
