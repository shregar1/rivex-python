"""``rivex.datastructures.abstraction`` — base data structure interface.

Provides ``IDataStructure``, the base interface for all Rivex container types.
"""

from __future__ import annotations

from abc import ABC


class IDataStructure(ABC):
    """Base interface for high-performance Rivex data structures."""

    pass


__all__ = ["IDataStructure"]
