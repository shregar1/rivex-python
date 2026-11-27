"""{{resource}} REST controller (Pydantic body, default)."""

from __future__ import annotations

from rivex import Body, Path, Query, delete, get, patch, post

from abstractions.controller import IController
from constants.api import API_PREFIX, {{resource_upper}}_TAG
from dtos.{{resource}} import (
{{dto_imports}}
)
from services.{{resource}} import (
{{service_imports}}
)
from utilities.timing import timer


class {{model_class}}sController(IController):
    """CRUD endpoints for the ``{{resource}}`` resource (Pydantic body)."""

    path = f"{API_PREFIX}/{{resource}}"
    tags = [{{resource_upper}}_TAG]

    @classmethod
    def base_path(cls) -> str:
        return cls.path

    @get("", summary="List {{resource}}")
    @timer("controller")
    async def list_{{resource}}(
        self,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict:
        request = List{{model_class}}sRequest(offset=offset, limit=limit)
        service = List{{model_class}}sService()
        return await self.invoke_service(service, request)

    @get("/{{{path_param}}}", summary="Fetch a {{singular}}")
    @timer("controller")
    async def get_{{singular}}(self, {{path_param}}: int = Path(ge=1)) -> dict:
        request = Get{{model_class}}Request({{path_param}}={{path_param}})
        service = Get{{model_class}}Service()
        return await self.invoke_service(service, request)

    @post("", summary="Create a {{singular}}")
    @timer("controller")
    async def create_{{singular}}(self, payload: Create{{model_class}}Request = Body()) -> dict:
        service = Create{{model_class}}Service()
        return await self.invoke_service(service, payload)

    @patch("/{{{path_param}}}", summary="Update a {{singular}}")
    @timer("controller")
    async def update_{{singular}}(
        self,
        {{path_param}}: int = Path(ge=1),
        payload: Update{{model_class}}Request = Body(),
    ) -> dict:
        request = Update{{model_class}}Request(
            {{path_param}}={{path_param}},
{{request_build_fields}}
        )
        service = Update{{model_class}}Service()
        return await self.invoke_service(service, request)

    @delete("/{{{path_param}}}", summary="Delete a {{singular}}")
    @timer("controller")
    async def delete_{{singular}}(self, {{path_param}}: int = Path(ge=1)) -> dict:
        request = Delete{{model_class}}Request({{path_param}}={{path_param}})
        service = Delete{{model_class}}Service()
        return await self.invoke_service(service, request)
