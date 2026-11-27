"""``rivex.utilities.crypto.abstraction`` — base class for crypto utilities."""

from __future__ import annotations

from abc import abstractmethod

from rivex.utilities.abstraction import LayeredUtility


class ICryptoUtility(LayeredUtility):
    """Base class for crypto domain utility layers."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Returns the class name."""
        raise NotImplementedError


__all__ = ["ICryptoUtility"]
