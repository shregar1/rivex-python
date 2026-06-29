"""Request DTO base."""

from __future__ import annotations

from dtos.base import ApplicationBaseModel, IDto


class IRequestDto(IDto, ApplicationBaseModel):
    """Inbound HTTP body / params schema. Concrete DTOs in submodules."""
