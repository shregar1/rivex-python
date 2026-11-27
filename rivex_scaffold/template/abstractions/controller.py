"""Controller contract — Rivex class-based HTTP handlers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from rivex import Controller, HTTPException, Request

from abstractions.context import ContextMixin
from abstractions.service import IService
from constants.logger import DOMAIN_ERROR, UNHANDLED_ERROR
from dtos.response import APIEnvelopeResponse
from errors import DomainError
from utilities.api_envelope import http_exception_detail


class IController(Controller, ContextMixin, ABC):
    """Base controller. All presentation controllers extend this."""

    path: str = ""
    tags: list[str] = []

    def __init__(self, **kwargs: Any) -> None:
        ContextMixin.__init__(self, **kwargs)

    @classmethod
    @abstractmethod
    def base_path(cls) -> str:
        """Route prefix for this controller (mirrors ``path``)."""

    def bind_request(self, request: Request, *, api_name: str | None = None) -> None:
        """Lift tracing fields from the Rivex request."""
        self.bind_request_context(
            urn=request.header("x-request-id", ""),
            user_urn=request.header("x-user-urn", ""),
            api_name=api_name or request.path,
            user_id=request.header("x-user-id"),
            method=request.method,
            path=request.path,
        )

    def bind_service(self, service: ContextMixin) -> None:
        """Propagate controller tracing context to a service instance."""
        service.bind_request_context(
            urn=self.urn,
            user_urn=self.user_urn,
            api_name=self.api_name,
            user_id=self.user_id,
            method=self.method,
            path=self.path,
        )

    async def invoke_service(
        self,
        service: IService[Any, Any],
        request: Any | None = None,
        /,
        **kwargs: Any,
    ) -> Any:
        """Bind context and run a service (handler should be decorated with :func:`timer`)."""
        self.bind_service(service)
        return await service.invoke(request, **kwargs)

    def handle_domain_error(self, err: DomainError) -> HTTPException:
        """Translate domain errors into Rivex HTTP exceptions."""
        self.logger.warn(
            "Domain error returned to client",
            code=DOMAIN_ERROR,
            error_code=err.code,
            error_message=err.message,
            status_code=err.status_code,
            controller=self.__class__.__name__,
            api_name=self.api_name or None,
        )
        envelope = APIEnvelopeResponse.from_domain_error(
            err,
            reference_urn=self.urn or None,
        )
        return HTTPException(
            status_code=err.status_code,
            detail=http_exception_detail(envelope),
        )

    def respond(self, data: Any, *, response_message: str = "OK", response_key: str = "SUCCESS") -> dict:
        """Wrap a successful handler payload in the standard API envelope."""
        envelope = APIEnvelopeResponse.success(
            data,
            response_message=response_message,
            response_key=response_key,
            reference_urn=self.urn or None,
        )
        return envelope.model_dump(by_alias=True, mode="json")

    def handle_exception(self, err: Exception) -> HTTPException:
        if isinstance(err, DomainError):
            return self.handle_domain_error(err)
        if isinstance(err, HTTPException):
            return err
        self.logger.exception(
            "Unhandled exception in controller",
            code=UNHANDLED_ERROR,
            exc=err,
            controller=self.__class__.__name__,
        )
        envelope = APIEnvelopeResponse.failed(
            "Internal server error",
            "INTERNAL_ERROR",
            reference_urn=self.urn or None,
        )
        return HTTPException(500, detail=http_exception_detail(envelope))
