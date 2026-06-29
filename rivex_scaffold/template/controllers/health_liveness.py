"""Liveness probe."""

from __future__ import annotations

from rivex import get

from abstractions.controller import IController
from configs import PROJECT_NAME, PROJECT_VERSION, project_metadata
from constants.api import HEALTH_TAG
from utilities.timing import timer


class HealthLivenessController(IController):
    path = "/health"
    tags = [HEALTH_TAG]

    @classmethod
    def base_path(cls) -> str:
        return cls.path

    @get("", summary="Liveness probe")
    @timer("controller")
    async def health_liveness(self) -> dict[str, str]:
        meta = project_metadata()
        return {
            "status": "ok",
            "service": meta.get("name", PROJECT_NAME),
            "version": meta.get("version", PROJECT_VERSION),
        }
