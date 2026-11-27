"""``rivex.constants.exception`` — exception constants sub-package.

Usage::

    from rivex.constants.exception import (
        IExceptionConstant, ExceptionStatus, ExceptionCode,
        ExceptionMessage, ExceptionKey,
    )
"""

from rivex.constants.exception.abstraction import IExceptionConstant
from rivex.constants.exception.code import ExceptionCode
from rivex.constants.exception.key import ExceptionKey
from rivex.constants.exception.message import ExceptionMessage
from rivex.constants.exception.status import ExceptionStatus

__all__ = [
    "IExceptionConstant",
    "ExceptionStatus",
    "ExceptionCode",
    "ExceptionKey",
    "ExceptionMessage",
]
