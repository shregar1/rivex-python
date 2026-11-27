"""``rivex.exceptions.domain.connection_failure`` — connection failure domain exception.
"""

from __future__ import annotations

from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.message import ExceptionMessage
from rivex.exceptions.http.service_unavailable import IServiceUnavailableException


class ConnectionFailureException(IServiceUnavailableException):
    """Raised when a connection to a downstream service or database cannot be established."""

    code: str = ExceptionCode.CONNECTION_FAILURE
    message: str = ExceptionMessage.CONNECTION_FAILURE


__all__ = ["ConnectionFailureException"]
