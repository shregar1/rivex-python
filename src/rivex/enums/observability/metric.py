"""``rivex.enums.observability.metric`` — metric type enum.
"""

from __future__ import annotations

from rivex.constants.observability.metric import MetricTypeConstant
from rivex.enums.observability.abstraction import IObservabilityEnum


class MetricType(str, IObservabilityEnum):
    """Metric type Enum built from ``MetricTypeConstant`` constants."""

    COUNTER = MetricTypeConstant.COUNTER
    GAUGE = MetricTypeConstant.GAUGE
    HISTOGRAM = MetricTypeConstant.HISTOGRAM


__all__ = ["MetricType"]
