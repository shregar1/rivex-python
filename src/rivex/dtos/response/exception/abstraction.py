"""``rivex.dtos.response.exception.abstraction`` — base exception response DTO interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Self

from rivex.dtos.response.abstraction import ResponseDTO


class IExceptionResponseDTO(ResponseDTO, ABC):
    """Base interface for all specialized Exception Response DTOs."""

    @classmethod
    @abstractmethod
    def from_exception(
        cls,
        err: Any,
        *,
        reference_urn: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """Construct a response DTO instance from an exception."""


__all__ = ["IExceptionResponseDTO"]
