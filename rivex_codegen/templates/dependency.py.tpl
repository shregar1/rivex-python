"""{{resource}} service-layer Rivex DI bindings (Pydantic backend)."""

from __future__ import annotations

from typing import Any

from abstractions.dependency import IDependency
from services.{{resource}} import (
    Create{{model_class}}Service,
    Delete{{model_class}}Service,
    Get{{model_class}}Service,
    List{{model_class}}sService,
    Update{{model_class}}Service,
)


class Create{{model_class}}ServiceDependency(IDependency):
    def resolve(self, *args: Any, **kwargs: Any) -> Create{{model_class}}Service:
        return Create{{model_class}}Service()


class Get{{model_class}}ServiceDependency(IDependency):
    def resolve(self, *args: Any, **kwargs: Any) -> Get{{model_class}}Service:
        return Get{{model_class}}Service()


class List{{model_class}}sServiceDependency(IDependency):
    def resolve(self, *args: Any, **kwargs: Any) -> List{{model_class}}sService:
        return List{{model_class}}sService()


class Update{{model_class}}ServiceDependency(IDependency):
    def resolve(self, *args: Any, **kwargs: Any) -> Update{{model_class}}Service:
        return Update{{model_class}}Service()


class Delete{{model_class}}ServiceDependency(IDependency):
    def resolve(self, *args: Any, **kwargs: Any) -> Delete{{model_class}}Service:
        return Delete{{model_class}}Service()
