"""Database connectivity probe."""

from __future__ import annotations

from ormx import get_engine
from rivex import get

from abstractions.controller import IController
from configs import PROJECT_NAME, project_metadata
from constants.api import HEALTH_TAG
from utilities.timing import timer


class HealthDbController(IController):
    path = "/health"
    tags = [HEALTH_TAG]

    @classmethod
    def base_path(cls) -> str:
        return cls.path

    @get("/db", summary="Database connectivity probe")
    @timer("controller")
    async def health_db(self) -> dict[str, str | int]:
        engine = get_engine()
        rows = await engine.fetch_many("SELECT 1 AS ok", [])
        return {
            "status": "ok",
            "service": project_metadata().get("name", PROJECT_NAME),
            "database": rows[0]["ok"],
        }
