"""Update a {{resource}}."""

from __future__ import annotations

from abstractions.service import IService
from constants.logger import {{resource_upper}}_UPDATED
from dtos.{{resource}} import Update{{model_class}}Request, Update{{model_class}}Response
from errors import NotFoundError
from repositories.{{resource}} import {{model_class}}Repository
from utilities.timing import timer


class Update{{model_class}}Service(IService[Update{{model_class}}Request, Update{{model_class}}Response]):
    """Apply a partial update to a {{resource}}."""

    def __init__(self, *, {{repo_var}}: {{model_class}}Repository | None = None) -> None:
        super().__init__()
        self._repo = {{repo_var}} or {{model_class}}Repository()

    @timer("service")
    async def run(self, request: Update{{model_class}}Request) -> Update{{model_class}}Response:
        item = await self._repo.find_by_id(request.{{resource}}_id)
        if item is None:
            raise NotFoundError("{{resource}}", str(request.{{resource}}_id))

{{update_fields}}

        saved = await self._repo.update(item)
        self.logger.info("{{model_class}} updated", code={{resource_upper}}_UPDATED, item_id=saved.id)
        return Update{{model_class}}Response(
{{response_fields}}
        )
