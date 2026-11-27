"""``rivex.enums.api`` — API domain enums package.
"""

from __future__ import annotations

from rivex.enums.api.abstraction import IAPIEnum
from rivex.enums.api.cookie import SameSitePolicy
from rivex.enums.api.method import HTTPMethodEnum
from rivex.enums.api.status import APIResult, APIStatus

__all__ = ["IAPIEnum", "APIResult", "APIStatus", "HTTPMethodEnum", "SameSitePolicy"]
