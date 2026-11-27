"""``rivex.enums.api.cookie`` — cookie policy enums.
"""

from __future__ import annotations

from rivex.enums.api.abstraction import IAPIEnum


class SameSitePolicy(str, IAPIEnum):
    """Cookie SameSite policy options."""

    LAX = "Lax"
    STRICT = "Strict"
    NONE = "None"


__all__ = ["SameSitePolicy"]
