"""Create a {{resource}}."""

from __future__ import annotations

from abstractions.service import IService
from constants.logger import {{resource_upper}}_CREATED
from dtos.{{resource}} import Create{{model_class}}Request, Create{{model_class}}Response
from models.{{resource}} import {{model_class}}
from repositories.{{resource}} import {{model_class}}Repository
from utilities.timing import timer


class Create{{model_class}}Service(IService[Create{{model_class}}Request, Create{{model_class}}Response]):
    """Persist a new {{resource}} and return its representation."""

    def __init__(self, *, {{repo_var}}: {{model_class}}Repository | None = None) -> None:
        super().__init__()
        self._repo = {{repo_var}} or {{model_class}}Repository()

    @timer("service")
    async def run(self, request: Create{{model_class}}Request) -> Create{{model_class}}Response:
        entity = {{model_class}}(
{{init_fields}}
        )
        saved = await self._repo.create(entity)
        self.logger.info(
            "{{model_class}} created",
            code={{resource_upper}}_CREATED,
            item_id=saved.id,
            urn=str(saved.urn),
        )
        return Create{{model_class}}Response(
{{response_fields}}
        )
