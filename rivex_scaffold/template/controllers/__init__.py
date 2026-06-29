"""Class-based HTTP controllers."""

from controllers.health_db import HealthDbController
from controllers.health_liveness import HealthLivenessController
from controllers.items import ItemsController

ALL_CONTROLLERS: tuple[type, ...] = (
    HealthLivenessController,
    HealthDbController,
    ItemsController,
)

__all__ = [
    "ALL_CONTROLLERS",
    "HealthDbController",
    "HealthLivenessController",
    "ItemsController",
]
