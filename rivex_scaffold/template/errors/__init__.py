"""Domain error types — one exception class per module."""

from errors.conflict_error import ConflictError
from errors.domain_error import DomainError
from errors.forbidden_error import ForbiddenError
from errors.not_found_error import NotFoundError
from errors.unauthorized_error import UnauthorizedError
from errors.validation_error import ValidationError

__all__ = [
    "ConflictError",
    "DomainError",
    "ForbiddenError",
    "NotFoundError",
    "UnauthorizedError",
    "ValidationError",
]
