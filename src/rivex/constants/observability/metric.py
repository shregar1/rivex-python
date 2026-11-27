"""``rivex.constants.observability.metric`` — metric type string constants.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.observability.abstraction import IObservabilityConstant


class MetricTypeConstant(IObservabilityConstant):
    """Metric type string constants."""

    COUNTER: Final[str] = "counter"
    GAUGE: Final[str] = "gauge"
    HISTOGRAM: Final[str] = "histogram"


__all__ = ["MetricTypeConstant"]
