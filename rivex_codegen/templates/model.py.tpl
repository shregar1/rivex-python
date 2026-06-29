"""{{model_class}} persistence model."""

from __future__ import annotations

from ormx import Field, StringField

from models.base import BaseModel


class {{model_class}}(BaseModel):
    """{{description}}"""

    __tablename__ = "{{table_name}}"

{{model_fields}}

    @classmethod
    def entity_type(cls) -> str:
        return "{{resource}}"
