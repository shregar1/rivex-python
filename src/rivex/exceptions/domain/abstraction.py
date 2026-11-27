"""``rivex.exceptions.domain.abstraction`` — base domain exception interface.
"""

from __future__ import annotations

from abc import ABC

from rivex.exceptions.base import RivexException


class IDomainException(RivexException, ABC):
    """Base interface for domain-specific exception classes."""

    pass


__all__ = ["IDomainException"]
