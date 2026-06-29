"""List {{resource}}s with pagination."""

from __future__ import annotations

from abstractions.service import IService
from constants.logger import {{resource_upper}}_LISTED
from dtos.{{resource}} import List{{model_class}}Request, List{{model_class}}Response
from mappers import {{resource}}_to_response
from repositories.{{resource}} import {{model_class}}Repository
from utilities.timing import timer


class List{{model_class}}sService(IService[List{{model_class}}Request, List{{model_class}}Response]):
    """Paginated list of {{resource}}s."""

    def __init__(self, *, {{repo_var}}: {{model_class}}Repository | None = None) -> None:
        super().__init__()
        self._repo = {{repo_var}} or {{model_class}}Repository()

    @timer("service")
    async def run(self, request: List{{model_class}}Request) -> List{{model_class}}Response:
        items = await self._repo.find_all(offset=request.offset, limit=request.limit)
        total = await self._repo.count()
        self.logger.info("{{model_class}}s listed", code={{resource_upper}}_LISTED, count=len(items), total=total)
        return List{{model_class}}Response(
            items=[{{resource}}_to_response(item) for item in items],
            total=total,
            offset=request.offset,
            limit=request.limit,
        )
