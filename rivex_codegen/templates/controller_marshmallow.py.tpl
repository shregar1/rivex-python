"""{{resource}} REST controller (Marshmallow body — no Pydantic)."""

from __future__ import annotations

from typing import Any

from rivex import Body, Path, Query, delete, get, patch, post

from abstractions.controller import IController
from constants.api import API_PREFIX, {{resource_upper}}_TAG
from dtos.{{resource}}.schemas import (
{{marshmallow_imports}}
)
from services.{{resource}} import (
{{service_imports}}
)
from utilities.timing import timer


class {{model_class}}sController(IController):
    """CRUD endpoints for the ``{{resource}}`` resource (Marshmallow body)."""

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
    async def create_{{singular}}(self, body: dict[str, Any] = Body()) -> dict:
        # Body is raw JSON; run it through the Marshmallow schema.
        data = create_{{resource}}_request_schema.load(body)
        request = Create{{model_class}}Request(**data)
        service = Create{{model_class}}Service()
        return await self.invoke_service(service, request)

    @patch("/{{{path_param}}}", summary="Update a {{singular}}")
    @timer("controller")
    async def update_{{singular}}(
        self,
        {{path_param}}: int = Path(ge=1),
        body: dict[str, Any] = Body(),
    ) -> dict:
        data = update_{{resource}}_request_schema.load(body)
        request = Update{{model_class}}Request({{path_param}}={{path_param}}, **data)
        service = Update{{model_class}}Service()
        return await self.invoke_service(service, request)

    @delete("/{{{path_param}}}", summary="Delete a {{singular}}")
    @timer("controller")
    async def delete_{{singular}}(self, {{path_param}}: int = Path(ge=1)) -> dict:
        request = Delete{{model_class}}Request({{path_param}}={{path_param}})
        service = Delete{{model_class}}Service()
        return await self.invoke_service(service, request)
