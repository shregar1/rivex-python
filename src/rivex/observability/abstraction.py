"""``rivex.observability.abstraction`` — base observability interface.

Provides ``IObservability`` base interface for metrics, tracing, and logging providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IObservability(ABC):
    """Base interface for observability extensions."""

    @abstractmethod
    def record_metric(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a telemetry metric."""
        raise NotImplementedError


__all__ = ["IObservability"]
