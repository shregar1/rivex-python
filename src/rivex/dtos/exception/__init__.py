"""``rivex.dtos.exception`` — Exception DTO sub-package.

Provides ``IExceptionDTO`` abstraction and concrete exception feedback DTOs
like ``ValidationErrorItem``.
"""

from __future__ import annotations

from rivex.dtos.exception.abstraction import IExceptionDTO
from rivex.dtos.exception.validation_error import ValidationErrorItem

__all__ = [
    "IExceptionDTO",
    "ValidationErrorItem",
]
