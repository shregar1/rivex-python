"""Schema backend renderers for the codegen.

The generator emits **native** code for the chosen schema backend:

* **pydantic** — Pydantic ``BaseModel`` subclasses; controller uses
  ``Body(CreateItemRequest)``; the framework does the rest.
* **schemax** — ``.schemax`` IDL file + ``schemax idl compile``-generated
  ``Message`` classes; controller uses ``Body(dict)`` and constructs
  ``Message.from_dict(body)`` explicitly. No Pydantic in the dependency
  tree.
* **marshmallow** — ``marshmallow.Schema`` subclasses; controller uses
  ``Body(dict)`` and calls ``schema.load(body)`` explicitly. No Pydantic
  in the dependency tree.

Public surface:

* :data:`SCHEMAS` — the supported backend names.
* :func:`available_schemas` — backends whose runtime dependency is importable.
* :func:`render_pydantic` — produces ``dtos/<resource>/requests.py`` content
  (Pydantic DTOs).
* :func:`render_schemax` — produces ``schemas/<resource>.schemax`` IDL content
  + the runnable instructions for ``schemax idl compile``.
* :func:`render_marshmallow` — produces ``dtos/<resource>/schemas.py`` content
  (Marshmallow ``Schema`` classes).
* :func:`render_for_backend` — dispatch helper.
"""

from __future__ import annotations

import importlib.util as _ilu
import sys as _sys
from pathlib import Path as _P
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Static type-checker view: import the real classes from the
    # installed ``rivex_codegen`` package so attribute access and
    # constructor calls are typed correctly.
    from rivex_codegen import FieldSpec, ResourceSpec


def _load_codegen_module():
    """Load :mod:`rivex_codegen` robustly.

    The codegen module is sometimes loaded by tests via ``importlib.util``
    which does not set ``__package__``, so relative imports fail. We try
    three strategies in order: a normal package import, a relative
    import, and finally loading the file directly.
    """
    # 1) Already imported.
    if "rivex_codegen" in _sys.modules:
        return _sys.modules["rivex_codegen"]
    # 2) Try the package import.
    try:
        import rivex_codegen as _cg

        return _cg
    except ImportError:
        pass
    # 3) Direct file load.
    path = _P(__file__).resolve().parent / "__init__.py"
    spec = _ilu.spec_from_file_location("rivex_codegen_under_test", path)
    mod = _ilu.module_from_spec(spec)
    _sys.modules["rivex_codegen_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


_codegen = _load_codegen_module()
if TYPE_CHECKING:
    pass  # FieldSpec / ResourceSpec imported above for the type checker.
else:
    FieldSpec = _codegen.FieldSpec
    ResourceSpec = _codegen.ResourceSpec

# At runtime mypy can't see the dynamically loaded classes, so the
# type-checker view is the only one that knows the shape of these
# names. The ``Any`` fallback is never used in production — it's
# here to keep the runtime import working when ``rivex_codegen`` is
# not installed.
_: Any = (FieldSpec, ResourceSpec)

# The well-known backend names. The form option and dispatch key.
PYDANTIC = "pydantic"
SCHEMAX = "schemax"
MARSHMALLOW = "marshmallow"

SCHEMAS: tuple[str, ...] = (PYDANTIC, SCHEMAX, MARSHMALLOW)


def available_schemas() -> list[str]:
    """Return the backends whose runtime dependency is importable."""
    out: list[str] = []
    try:
        from pydantic import BaseModel  # noqa: F401

        out.append(PYDANTIC)
    except ImportError:
        pass
    try:
        from schemax.idl.runtime import Message  # noqa: F401

        out.append(SCHEMAX)
    except ImportError:
        pass
    try:
        from marshmallow import Schema  # noqa: F401

        out.append(MARSHMALLOW)
    except ImportError:
        pass
    return out


# ---------------------------------------------------------------------------
# Field → Python type helpers
# ---------------------------------------------------------------------------


_PY_TO_PY: dict[str, str] = {
    "str": "str",
    "int": "int",
    "float": "float",
    "bool": "bool",
    "bytes": "bytes",
    "datetime": "datetime",
    "date": "date",
    "time": "time",
    "UUID": "UUID",
    "uuid": "UUID",
}


def _split_py_type(py: str) -> tuple[str, bool, bool]:
    """Return ``(base, repeated, optional)`` from a Python type annotation.

    Recognises ``list[X]`` and ``X | None`` / ``Optional[X]`` wrappers.
    """
    p = py.strip()
    repeated = False
    if p.startswith("list[") and p.endswith("]"):
        repeated = True
        p = p[5:-1].strip()
    optional = False
    if p.endswith(" | None"):
        optional = True
        p = p[:-7].strip()
    elif p.startswith("Optional[") and p.endswith("]"):
        optional = True
        p = p[9:-1].strip()
    return p, repeated, optional


# ---------------------------------------------------------------------------
# Aggregation: walk the endpoints and collect fields per DTO
# ---------------------------------------------------------------------------


def _aggregate_dtos(spec: ResourceSpec) -> dict[str, list[FieldSpec]]:
    """Group fields by DTO name.

    Returns a dict like::

        {
            "CreateItemRequest":  [...body fields...],
            "UpdateItemRequest":  [...patch fields...],
            "ListItemsRequest":   [...query fields...],
            "GetItemRequest":     [...path param...],
            "DeleteItemRequest":  [...path param...],
            "ItemResponse":       [...response fields...],
            "CreateItemResponse": [...],
            "UpdateItemResponse": [...],
            "ListItemsResponse":  [...],
            "DeleteItemResponse": [...],
        }
    """
    model_class = spec.model_class
    resource = spec.resource
    out: dict[str, list[FieldSpec]] = {}

    body_create: list[FieldSpec] = []
    body_update: list[FieldSpec] = []
    query_list: list[FieldSpec] = []
    response_single: list[FieldSpec] = []
    body_seen: set[str] = set()
    query_seen: set[str] = set()
    response_seen: set[str] = set()
    for ep in spec.endpoints:
        for f in ep.body_fields + ep.form_fields:
            if ep.method == "PATCH" and f.name not in body_seen:
                body_update.append(f)
            elif f.name not in body_seen:
                body_create.append(f)
            body_seen.add(f.name)
        for f in ep.query_params:
            if f.name not in query_seen:
                query_list.append(f)
            query_seen.add(f.name)
        if ep.method in {"GET", "POST", "PATCH"} and ep.response_fields:
            for f in ep.response_fields:
                if f.name not in response_seen:
                    response_single.append(f)
                    response_seen.add(f.name)
    if not response_single:
        response_single = [
            FieldSpec(name="id", py_type="int", required=True),
            FieldSpec(name="urn", py_type="UUID", required=True),
            FieldSpec(name="created_at", py_type="datetime", required=False, default="None"),
            FieldSpec(name="updated_at", py_type="datetime", required=False, default="None"),
        ]

    singular = resource[:-1] if resource.endswith("s") and len(resource) > 1 else resource
    singular_id = f"{singular}_id"

    if body_create:
        out[f"Create{model_class}Request"] = body_create
    if body_update or any(ep.method == "PATCH" for ep in spec.endpoints):
        if not body_update:
            body_update = list(body_create)
        out[f"Update{model_class}Request"] = body_update
    if query_list or any(ep.method == "GET" and not ep.path_params for ep in spec.endpoints):
        if not query_list:
            query_list = [
                FieldSpec(name="offset", py_type="int", required=True, default="0", ge=0),
                FieldSpec(name="limit", py_type="int", required=True, default="50", ge=1, le=200),
            ]
        out[f"List{model_class}sRequest"] = query_list
    if any(ep.method == "GET" and ep.path_params for ep in spec.endpoints):
        out[f"Get{model_class}Request"] = [
            FieldSpec(name=singular_id, py_type="int", required=True, ge=1)
        ]
    if any(ep.method == "DELETE" for ep in spec.endpoints):
        out[f"Delete{model_class}Request"] = [
            FieldSpec(name=singular_id, py_type="int", required=True, ge=1)
        ]

    if any(ep.method == "DELETE" for ep in spec.endpoints):
        out[f"Delete{model_class}Response"] = [
            FieldSpec(name=singular_id, py_type="int", required=True),
            FieldSpec(name="deleted", py_type="bool", required=True, default="True"),
        ]
    if any(ep.method == "POST" for ep in spec.endpoints):
        out[f"Create{model_class}Response"] = [
            FieldSpec(name="id", py_type="int", required=True),
            FieldSpec(name="urn", py_type="UUID", required=True),
        ] + [f for f in response_single if f.name not in {"id", "urn"}]
    if any(ep.method == "PATCH" for ep in spec.endpoints):
        out[f"Update{model_class}Response"] = response_single
    out[f"{model_class}Response"] = response_single
    if any(ep.method == "GET" and not ep.path_params for ep in spec.endpoints):
        out[f"List{model_class}sResponse"] = [
            FieldSpec(name="items", py_type=f"list[{model_class}Response]", required=True),
            FieldSpec(name="total", py_type="int", required=True),
            FieldSpec(name="offset", py_type="int", required=True),
            FieldSpec(name="limit", py_type="int", required=True),
        ]

    return out


# ---------------------------------------------------------------------------
# Pydantic renderer
# ---------------------------------------------------------------------------


def _py_default(f: FieldSpec) -> str:
    """Return a Python-source default expression for *f*.

    Bool defaults come in as the strings ``"true"`` / ``"false"`` from the
    form parser; we normalise them to ``True`` / ``False`` so the rendered
    code parses (e.g. ``load_default=False`` in Marshmallow). Pydantic
    accepts either spelling, but using the Python spelling keeps both
    backends consistent.
    """
    if f.py_type == "bool" and f.default is not None:
        lowered = f.default.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return "True"
        if lowered in {"false", "0", "no"}:
            return "False"
    return f.default or ""


def _py_field_kwargs(f: FieldSpec) -> str:
    parts: list[str] = []
    if f.default is not None:
        parts.append(f"default={_py_default(f)}")
    elif not f.required:
        parts.append("default=None")
    if f.max_length is not None:
        parts.append(f"max_length={f.max_length}")
    if f.min_length is not None:
        parts.append(f"min_length={f.min_length}")
    if f.ge is not None:
        parts.append(f"ge={f.ge}")
    if f.le is not None:
        parts.append(f"le={f.le}")
    if f.description:
        parts.append(f'description="{f.description}"')
    return ", ".join(parts)


def _py_field_line(f: FieldSpec) -> str:
    kwargs = _py_field_kwargs(f)
    if kwargs:
        return f"    {f.name}: {f.py_type} = Field({kwargs})"
    return f"    {f.name}: {f.py_type}"


def _pydantic_class(name: str, fields: list[FieldSpec], *, base: str) -> str:
    body = "\n".join(_py_field_line(f) for f in fields) or "    pass"
    return f"class {name}({base}):\n{body}\n"


def render_pydantic(spec: ResourceSpec) -> dict[str, str]:
    """Render ``dtos/<resource>/requests.py`` (Pydantic) for *spec*."""
    dtos = _aggregate_dtos(spec)

    request_keys = [k for k in dtos if k.endswith("Request")]
    response_keys = [k for k in dtos if k.endswith("Response")]

    blocks: list[str] = [
        '"""Item request / response DTOs."""',
        "",
        "from __future__ import annotations",
        "",
        "from datetime import datetime, date, time",
        "from uuid import UUID",
        "",
        "from rivex import Field",
        "",
        "from dtos.base import ApplicationBaseModel",
        "from dtos.requests import IRequestDto",
        "",
    ]
    for name in request_keys:
        blocks.append(_pydantic_class(name, dtos[name], base="IRequestDto").rstrip())
        blocks.append("")
    for name in response_keys:
        blocks.append(_pydantic_class(name, dtos[name], base="ApplicationBaseModel").rstrip())
        blocks.append("")
    blocks.append("__all__ = [")
    for k in request_keys + response_keys:
        blocks.append(f'    "{k}",')
    blocks.append("]")
    blocks.append("")
    return {"dtos": "\n".join(blocks)}


# ---------------------------------------------------------------------------
# Schemax renderer
# ---------------------------------------------------------------------------


_SCHEMAX_TYPE = {
    "str": "string",
    "int": "int64",
    "float": "double",
    "bool": "bool",
    "bytes": "bytes",
    "datetime": "timestamp",
    "date": "string",  # ISO 8601 date string
    "time": "string",  # ISO 8601 time string
    "UUID": "uuid",
    "uuid": "uuid",
}


def _py_to_schemax_type(py: str) -> tuple[str, bool, bool]:
    """Return ``(schemax_type, repeated, optional)`` from a Python type."""
    base, repeated, optional = _split_py_type(py)
    schemax_type = _SCHEMAX_TYPE.get(base, base)
    return schemax_type, repeated, optional


def _schemax_emit_message(name: str, fields: list[FieldSpec]) -> str:
    """Render one ``message`` block."""
    out = [f"message {name} {{"]
    for i, f in enumerate(fields, start=1):
        s_type, repeated, optional = _py_to_schemax_type(f.py_type)
        prefix = "repeated " if repeated else ("optional " if optional else "")
        out.append(f"    {prefix}{s_type} {f.name} = {i};")
    out.append("}")
    return "\n".join(out)


def render_schemax(spec: ResourceSpec) -> dict[str, str]:
    """Render the Schemax IDL file content for *spec*.

    The controller (in :mod:`rivex._codegen_templates.controller_schemax`) calls
    ``Message.from_dict(body)`` on the raw request body — no Pydantic is
    involved at runtime.
    """
    model_class = spec.model_class
    resource = spec.resource
    dtos = _aggregate_dtos(spec)

    out: list[str] = [
        f"// Generated by Rivex admin codegen for resource '{resource}'.",
        "// To regenerate the typed Python module, run:",
        f"//   schemax idl compile schemas/{resource}.schemax",
        "//",
        "// The controller imports the generated classes from the",
        f"// ``schemas.{resource}_pb`` module.",
        f"package {resource}.v1;",
        "",
    ]

    # Entity message
    out.append(f"/// {model_class} entity.")
    out.append(_schemax_emit_message(model_class, dtos[f"{model_class}Response"]))
    out.append("")

    # Request messages
    request_keys = [k for k in dtos if k.endswith("Request")]
    for name in request_keys:
        out.append(_schemax_emit_message(name, dtos[name]))
        out.append("")

    # Response messages
    response_keys = [k for k in dtos if k.endswith("Response")]
    for name in response_keys:
        if name == f"List{model_class}sResponse":
            # The list response uses `repeated Entity` instead of a single body.
            out.append(f"message {name} {{")
            out.append(f"    repeated {model_class} items = 1;")
            out.append("    int64 total = 2;")
            out.append("    int64 offset = 3;")
            out.append("    int64 limit = 4;")
            out.append("}")
        else:
            out.append(_schemax_emit_message(name, dtos[name]))
        out.append("")

    # Service declaration — the Rivex controller implements each RPC.
    out.append(f"service {model_class}Service {{")
    for ep in spec.endpoints:
        if ep.method == "GET" and not ep.path_params:
            out.append(
                f"    rpc List{model_class}s(List{model_class}sRequest) returns (List{model_class}sResponse);"
            )
        elif ep.method == "GET" and ep.path_params:
            out.append(
                f"    rpc Get{model_class}(Get{model_class}Request) returns ({model_class});"
            )
        elif ep.method == "POST":
            out.append(
                f"    rpc Create{model_class}(Create{model_class}Request) returns (Create{model_class}Response);"
            )
        elif ep.method == "PATCH":
            out.append(
                f"    rpc Update{model_class}(Update{model_class}Request) returns ({model_class});"
            )
        elif ep.method == "DELETE":
            out.append(
                f"    rpc Delete{model_class}(Delete{model_class}Request) returns (Delete{model_class}Response);"
            )
    out.append("}")
    out.append("")
    return {
        "schemax_idl": "\n".join(out),
        "schemax_compile_hint": (
            f"# Compile the IDL with: schemax idl compile schemas/{resource}.schemax\n"
        ),
    }


# ---------------------------------------------------------------------------
# Marshmallow renderer
# ---------------------------------------------------------------------------


def _mm_field_line(f: FieldSpec) -> str:
    base, repeated, _optional = _split_py_type(f.py_type)
    mapping = {
        "str": "fields.String",
        "int": "fields.Integer",
        "float": "fields.Float",
        "bool": "fields.Boolean",
        "bytes": "fields.Raw",
        "datetime": "fields.DateTime",
        "date": "fields.Date",
        "time": "fields.Time",
        "UUID": "fields.UUID",
        "uuid": "fields.UUID",
    }
    inner = mapping.get(base, "fields.Raw")
    kwargs: list[str] = []
    if f.required and not repeated:
        kwargs.append("required=True")
    else:
        kwargs.append("required=False")
    if f.default is not None and not f.required:
        kwargs.append(f"load_default={_py_default(f)}")
    if f.max_length is not None and base == "str":
        kwargs.append(f"validate=validate.Length(max={f.max_length})")
    if f.min_length is not None and base == "str":
        kwargs.append(f"validate=validate.Length(min={f.min_length})")
    if f.ge is not None and base in ("int", "float"):
        kwargs.append(f"validate=validate.Range(min={f.ge})")
    if f.le is not None and base in ("int", "float"):
        kwargs.append(f"validate=validate.Range(max={f.le})")
    call = f"{inner}({', '.join(kwargs)})"
    if repeated:
        return f"    {f.name} = fields.List({call})"
    return f"    {f.name} = {call}"


def _mm_class(name: str, fields: list[FieldSpec]) -> str:
    body = "\n".join(_mm_field_line(f) for f in fields) or "    pass"
    return f'class {name}Schema(Schema):\n    """Marshmallow schema for {name}."""\n{body}\n'


def render_marshmallow(spec: ResourceSpec) -> dict[str, str]:
    """Render Marshmallow ``Schema`` classes for *spec*.

    The controller calls ``<Schema>().load(body)`` to coerce the request.
    """
    model_class = spec.model_class
    resource = spec.resource
    dtos = _aggregate_dtos(spec)

    request_keys = [k for k in dtos if k.endswith("Request")]
    response_keys = [k for k in dtos if k.endswith("Response")]

    blocks: list[str] = [
        f'"""Marshmallow schemas for the {resource} resource."""',
        "",
        "from __future__ import annotations",
        "",
        "from marshmallow import Schema, fields, validate",
        "",
    ]
    for name in request_keys:
        blocks.append(_mm_class(name, dtos[name]).rstrip())
        blocks.append("")
    for name in response_keys:
        if name == f"List{model_class}sResponse":
            # The list response wraps a list of single-entity responses —
            # render a dedicated schema instead of a one-field model.
            entity = f"{model_class}ResponseSchema"
            blocks.append(
                f"class {name}Schema(Schema):\n"
                f'    """Marshmallow schema for {name}."""\n'
                f"    items = fields.List(fields.Nested({entity}()), required=True)\n"
                f"    total = fields.Integer(required=True)\n"
                f"    offset = fields.Integer(required=True)\n"
                f"    limit = fields.Integer(required=True)\n"
            )
        else:
            blocks.append(_mm_class(name, dtos[name]).rstrip())
        blocks.append("")

    blocks.append("# Convenience instances — instantiate, then ``.load(body)``.")
    blocks.append("")
    for name in request_keys + response_keys:
        var = _mm_instance_name(name, model_class, spec.resource)
        blocks.append(f"{var}_schema = {name}Schema()")
    blocks.append("")
    return {"marshmallow_schemas": "\n".join(blocks)}


def _snake(name: str) -> str:
    """PascalCase → snake_case."""
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _mm_instance_name(name: str, model_class: str, resource: str) -> str:
    """Build the convenience-instance variable name for a Marshmallow schema.

    ``CreateItemRequest`` + resource ``items`` → ``create_items_request``.
    The model's plural form (``items``) replaces the singular (``Item``) so
    that ``list_items`` and ``create_items`` use the same noun.
    """
    snake = _snake(name)
    singular = _snake(model_class)
    if singular in snake and resource != singular:
        snake = snake.replace(singular, resource, 1)
    return snake


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def render_for_backend(spec: ResourceSpec, backend: str) -> dict[str, str]:
    """Dispatch to the renderer for *backend*.

    The returned dict always has a ``"controller"`` key with the rendered
    controller file content, plus backend-specific extra keys.
    """
    if backend not in SCHEMAS:
        raise ValueError(f"unknown schema backend: {backend!r}. Available: {', '.join(SCHEMAS)}")
    if backend == PYDANTIC:
        return render_pydantic(spec)
    if backend == SCHEMAX:
        return render_schemax(spec)
    if backend == MARSHMALLOW:
        return render_marshmallow(spec)
    raise ValueError(backend)  # unreachable


__all__ = [
    "MARSHMALLOW",
    "PYDANTIC",
    "SCHEMAS",
    "SCHEMAX",
    "available_schemas",
    "render_for_backend",
    "render_marshmallow",
    "render_pydantic",
    "render_schemax",
]
