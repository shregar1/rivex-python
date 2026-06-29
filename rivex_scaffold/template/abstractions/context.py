"""Shared request context for controllers, services, utilities, and errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from utilities.logger_adapter import AppLogger


class ContextMixin:
    """Carries per-request tracing and identity fields across layers."""

    def __init__(
        self,
        *,
        urn: str | None = None,
        user_urn: str | None = None,
        api_name: str | None = None,
        user_id: str | None = None,
        method: str | None = None,
        path: str | None = None,
        logger: AppLogger | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._urn = urn or ""
        self._user_urn = user_urn or ""
        self._api_name = api_name or ""
        self._user_id = user_id
        self._method = method or ""
        self._path = path or ""
        self._logger = logger or self._create_logger()
        if any((urn, user_urn, api_name, user_id, method, path)):
            self._rebind_logger()

    @staticmethod
    def _create_logger() -> AppLogger:
        from utilities.logger_adapter import get_logger

        return get_logger(component=ContextMixin.__name__)

    @property
    def urn(self) -> str:
        return self._urn

    @urn.setter
    def urn(self, value: str) -> None:
        self._urn = value
        self._rebind_logger()

    @property
    def user_urn(self) -> str:
        return self._user_urn

    @user_urn.setter
    def user_urn(self, value: str) -> None:
        self._user_urn = value
        self._rebind_logger()

    @property
    def api_name(self) -> str:
        return self._api_name

    @api_name.setter
    def api_name(self, value: str) -> None:
        self._api_name = value
        self._rebind_logger()

    @property
    def user_id(self) -> str | None:
        return self._user_id

    @user_id.setter
    def user_id(self, value: str | None) -> None:
        self._user_id = value
        self._rebind_logger()

    @property
    def method(self) -> str:
        return self._method

    @method.setter
    def method(self, value: str) -> None:
        self._method = value
        self._rebind_logger()

    @property
    def path(self) -> str:
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        self._path = value
        self._rebind_logger()

    @property
    def logger(self) -> AppLogger:
        return self._logger

    @logger.setter
    def logger(self, value: AppLogger) -> None:
        self._logger = value

    def _rebind_logger(self) -> None:
        from utilities.logger_adapter import bind_logger

        self._logger = bind_logger(
            urn=self._urn,
            user_urn=self._user_urn,
            api_name=self._api_name,
            user_id=self._user_id,
            method=self._method,
            path=self._path,
            component=self.__class__.__name__,
        )

    def request_context_fields(self) -> dict[str, Any]:
        """Structured request fields for timing and repository logs."""
        fields: dict[str, Any] = {}
        if self._urn:
            fields["request_id"] = self._urn
        if self._api_name:
            fields["api_name"] = self._api_name
        if self._user_id:
            fields["user_id"] = self._user_id
        if self._user_urn:
            fields["user_urn"] = self._user_urn
        if self._method:
            fields["method"] = self._method
        if self._path:
            fields["path"] = self._path
        return fields

    def bound_log_fields(self) -> dict[str, Any]:
        """All context fields bound on the logger, for explicit and timed logs."""
        fields = self.request_context_fields()
        component = self.__class__.__name__
        if component != "ContextMixin":
            fields["component"] = component
        return fields

    def bind_request_context(
        self,
        *,
        urn: str | None = None,
        user_urn: str | None = None,
        api_name: str | None = None,
        user_id: str | None = None,
        method: str | None = None,
        path: str | None = None,
        propagate: bool = True,
    ) -> None:
        if urn is not None:
            self.urn = urn
        if user_urn is not None:
            self.user_urn = user_urn
        if api_name is not None:
            self.api_name = api_name
        if user_id is not None:
            self.user_id = user_id
        if method is not None:
            self.method = method
        if path is not None:
            self.path = path
        if propagate:
            self._propagate_request_context()

    def _propagate_request_context(self) -> None:
        context = {
            "urn": self._urn or None,
            "user_urn": self._user_urn or None,
            "api_name": self._api_name or None,
            "user_id": self._user_id,
            "method": self._method or None,
            "path": self._path or None,
            "propagate": False,
        }
        for value in self.__dict__.values():
            if isinstance(value, ContextMixin):
                value.bind_request_context(**context)
