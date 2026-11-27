"""``rivex.exceptions.domain`` — domain-specific exception classes package.
"""

from __future__ import annotations

from rivex.exceptions.domain.abstraction import IDomainException
from rivex.exceptions.domain.concurrency_conflict import ConcurrencyConflictException
from rivex.exceptions.domain.connection_failure import ConnectionFailureException
from rivex.exceptions.domain.constraint_violation import ConstraintViolationException
from rivex.exceptions.domain.database_timeout import DatabaseTimeoutException
from rivex.exceptions.domain.duplicate_key import DuplicateKeyException

__all__ = [
    "IDomainException",
    "ConcurrencyConflictException",
    "DuplicateKeyException",
    "DatabaseTimeoutException",
    "ConstraintViolationException",
    "ConnectionFailureException",
]
