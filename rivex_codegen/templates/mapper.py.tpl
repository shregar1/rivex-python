"""ORM ↔ DTO mapping for the {{resource}} slice."""

from __future__ import annotations

from models.{{resource}} import {{model_class}}

from dtos.response.{{resource}} import {{model_class}}Response


def {{resource}}_to_response(item: {{model_class}}) -> {{model_class}}Response:
    return {{model_class}}Response(
{{response_mapping_fields}}
    )


def {{resource}}s_to_response(items: list[{{model_class}}]) -> list[{{model_class}}Response]:
    return [{{resource}}_to_response(item) for item in items]


__all__ = ["{{resource}}_to_response", "{{resource}}s_to_response"]
