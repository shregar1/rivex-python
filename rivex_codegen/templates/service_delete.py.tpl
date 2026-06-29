"""Soft-delete a {{resource}}."""

from __future__ import annotations

from abstractions.service import IService
from constants.logger import {{resource_upper}}_DELETED
from dtos.{{resource}} import Delete{{model_class}}Request, Delete{{model_class}}Response
from errors import NotFoundError
from repositories.{{resource}} import {{model_class}}Repository
from utilities.timing import timer


class Delete{{model_class}}Service(IService[Delete{{model_class}}Request, Delete{{model_class}}Response]):
    """Mark a {{resource}} as deleted (soft delete)."""

    def __init__(self, *, {{repo_var}}: {{model_class}}Repository | None = None) -> None:
        super().__init__()
        self._repo = {{repo_var}} or {{model_class}}Repository()

    @timer("service")
    async def run(self, request: Delete{{model_class}}Request) -> Delete{{model_class}}Response:
        deleted = await self._repo.delete(request.{{resource}}_id)
        if not deleted:
            raise NotFoundError("{{resource}}", str(request.{{resource}}_id))
        self.logger.info("{{model_class}} deleted", code={{resource_upper}}_DELETED, item_id=request.{{resource}}_id)
        return Delete{{model_class}}Response(item_id=request.{{resource}}_id, deleted=True)
