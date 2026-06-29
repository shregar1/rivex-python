"""Contract layer — interfaces every layer implements."""

from abstractions.configuration import IConfiguration
from abstractions.factory import IFactory
from abstractions.error import IError
from abstractions.model import IModel
from abstractions.repository import IRepository
from abstractions.service import IService
from abstractions.singleton import SingletonMeta
from abstractions.utility import IUtility
from errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)

__all__ = [
    "IConfiguration",
    "IError",
    "IFactory",
    "IModel",
    "IRepository",
    "IService",
    "IUtility",
    "SingletonMeta",
    "DomainError",
    "NotFoundError",
    "UnauthorizedError",
    "ForbiddenError",
    "ValidationError",
    "ConflictError",
]

# Lazy / optional exports — import submodules directly when needed:
#   from abstractions.context import ContextMixin
#   from abstractions.controller import IController
#   from abstractions.dependency import IDependency
#   from abstractions.logger import ILogger
#   from utilities.logger_adapter import init_logging, get_logger
