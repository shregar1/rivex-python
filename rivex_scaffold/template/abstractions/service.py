"""Service contract — application / domain orchestration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from abstractions.context import ContextMixin
from dtos.requests import IRequestDto
from dtos.response import IResponseDto

TRequest = TypeVar("TRequest", bound=IRequestDto)
TResponse = TypeVar("TResponse", bound=IResponseDto)


class IService(ContextMixin, ABC, Generic[TRequest, TResponse]):
    """Business logic unit. Implementations live in ``services/``.

    Decorate each ``run`` implementation with ``@timer("service")``.
    """

    @abstractmethod
    async def run(self, request: TRequest) -> TResponse:
        """Execute the use case."""

    async def invoke(self, request: Any | None = None, /, **kwargs: Any) -> Any:
        """Run the use case (``run`` should be decorated with :func:`timer`)."""
        return await self.run(request, **kwargs)  # type: ignore[misc]

    async def execute(self, request: TRequest, **context: Any) -> TResponse:
        """Bind request context, then invoke."""
        self.bind_request_context(**context)
        return await self.invoke(request)
