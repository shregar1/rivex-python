"""Fetch a single {{resource}} by id."""

from __future__ import annotations

from abstractions.service import IService
from constants.logger import {{resource_upper}}_FETCHED
from dtos.{{resource}} import Get{{model_class}}Request, Get{{model_class}}Response
from errors import NotFoundError
from repositories.{{resource}} import {{model_class}}Repository
from utilities.timing import timer


class Get{{model_class}}Service(IService[Get{{model_class}}Request, Get{{model_class}}Response]):
    """Return a single {{resource}} or raise ``NotFoundError``."""

    def __init__(self, *, {{repo_var}}: {{model_class}}Repository | None = None) -> None:
        super().__init__()
        self._repo = {{repo_var}} or {{model_class}}Repository()

    @timer("service")
    async def run(self, request: Get{{model_class}}Request) -> Get{{model_class}}Response:
        item = await self._repo.find_by_id(request.{{resource}}_id)
        if item is None:
            raise NotFoundError("{{resource}}", str(request.{{resource}}_id))
        self.logger.info("{{model_class}} fetched", code={{resource_upper}}_FETCHED, item_id=item.id)
        return Get{{model_class}}Response(
{{response_fields}}
        )
