"""{{resource}} response DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from rivex import Field

from dtos.base import ApplicationBaseModel

{{response_classes}}

__all__ = [
{{response_exports}}
]
