"""Resource scaffolder — turns an API spec into a layered code plan.

Public surface:

* :class:`FieldSpec` — a single field in a DTO or model.
* :class:`EndpointSpec` — a parsed API endpoint (method, path, params, body, form, response).
* :class:`ResourceSpec` — collection of endpoints + resource-level metadata.
* :class:`CodePlan` — output of :func:`generate_resource`; a list of files to write.
* :func:`parse_api_form` — convert the admin form fields into a :class:`ResourceSpec`.
* :func:`generate_resource` — turn a :class:`ResourceSpec` into a :class:`CodePlan`.
* :func:`apply_plan` — write a :class:`CodePlan` to disk, safely.
* :func:`plan_to_preview_html` — render the plan as HTML for the admin UI.
* :func:`plan_to_summary` — one-line summary used in the dashboard banner.

The generator is intentionally template-driven: each file in the layered
architecture has a matching ``.tpl`` in :data:`TEMPLATES_DIR`. Substitutions use
the same ``{{key}}`` placeholder syntax as the project scaffolder.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


# ---------------------------------------------------------------------------
# Field + endpoint + resource specs
# ---------------------------------------------------------------------------


# A small whitelist of valid Python types we know how to render. Anything else
# falls back to a string annotation, which is the safest default.
_KNOWN_TYPES = {
    "str",
    "int",
    "float",
    "bool",
    "bytes",
    "datetime",
    "date",
    "time",
    "uuid",
    "UUID",
}


@dataclass(frozen=True)
class FieldSpec:
    """One field in a DTO or model."""

    name: str
    py_type: str  # "str", "int", "bool", "list[str]", "dict[str, int]", ...
    required: bool = True
    default: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    ge: int | float | None = None
    le: int | float | None = None
    description: str = ""
    # Where the field lives. ``model`` fields are persisted; ``body`` / ``query``
    # / ``path`` / ``form`` fields are DTO-only; ``response`` fields are
    # DTO-only on the output side.
    scopes: frozenset[str] = field(default_factory=frozenset)

    def has_scope(self, *names: str) -> bool:
        return any(n in self.scopes for n in names)


def _normalize_type(raw: str) -> str:
    """Map a user-supplied type hint to a known Python type annotation."""
    t = raw.strip()
    if not t:
        return "str"
    # Already a known scalar
    if t in _KNOWN_TYPES:
        return "UUID" if t.lower() == "uuid" else t
    # Common abbreviations
    aliases = {
        "string": "str",
        "integer": "int",
        "boolean": "bool",
        "number": "float",
        "object": "dict",
    }
    if t.lower() in aliases:
        return aliases[t.lower()]
    # Container types: list[X], dict[str, X], Optional[X], etc. — accept as-is.
    return t


def _strip_default_quotes(value: str) -> str:
    """Drop surrounding quotes from a default value (e.g. ``"foo"`` -> ``foo``)."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {"'", '"'}:
        return v[1:-1]
    return v


# Line format: ``name: type[:flags] [scope]``
#   flags: required|optional, default=<py>, max=<n>, min=<n>, ge=<n>, le=<n>, description="..."
#   scope: (body), (query), (path), (form), (response), (model), or comma-joined
# Default scope: (body, response, model) — i.e. present in the model + DTO.
_HEAD_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*"
    r"(?P<type>[^\s:#]+(?:\[[^\]]+\])?)"
    r"(?P<rest>.*)$"
)
_SCOPE_RE = re.compile(r"\(([^)]*)\)\s*$")
_FLAGS_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)(?:=([^\s,()][^,()]*?))?(?=\s*:|\s*\(|\s*$)")


def parse_field_line(line: str) -> FieldSpec:
    """Parse a single field line. Raises :class:`ValueError` for invalid input."""
    raw = line.strip()
    if not raw or raw.startswith("#"):
        raise ValueError("empty or comment line")
    m = _HEAD_RE.match(raw)
    if not m:
        raise ValueError(f"unrecognised field line: {line!r}")
    name = m.group("name")
    py_type = _normalize_type(m.group("type"))
    rest = m.group("rest") or ""

    # Extract trailing scope annotation: "(body, query)"
    scopes: set[str] = set()
    scope_match = _SCOPE_RE.search(rest)
    if scope_match:
        for piece in scope_match.group(1).split(","):
            piece = piece.strip().lower()
            if piece:
                scopes.add(piece)
        rest = rest[: scope_match.start()].rstrip()

    # Parse the remaining flag tokens: :key or :key=value. We prepend a
    # sentinel colon so the regex (which requires one) finds the first flag
    # even when the line starts with one immediately after the type.
    required = True
    default: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    ge: int | float | None = None
    le: int | float | None = None
    description = ""
    if not rest.startswith(":"):
        rest = ":" + rest
    for m_flag in _FLAGS_RE.finditer(rest):
        key = m_flag.group(1)
        value = m_flag.group(2)
        if value is not None:
            value = value.rstrip(",: ")
        if key == "required":
            required = True
        elif key == "optional":
            required = False
        elif key == "default" and value is not None:
            default = _strip_default_quotes(value)
            required = False
        elif key == "max" and value is not None:
            try:
                max_length = int(value)
            except ValueError as exc:
                raise ValueError(f"invalid max={value!r}") from exc
        elif key == "min" and value is not None:
            try:
                min_length = int(value)
            except ValueError as exc:
                raise ValueError(f"invalid min={value!r}") from exc
        elif key == "ge" and value is not None:
            try:
                ge = int(value) if "." not in value else float(value)
            except ValueError as exc:
                raise ValueError(f"invalid ge={value!r}") from exc
        elif key == "le" and value is not None:
            try:
                le = int(value) if "." not in value else float(value)
            except ValueError as exc:
                raise ValueError(f"invalid le={value!r}") from exc
        elif key == "description" and value is not None:
            description = _strip_default_quotes(value)

    if not scopes:
        scopes = {"body", "response", "model"}

    return FieldSpec(
        name=name,
        py_type=py_type,
        required=required,
        default=default,
        min_length=min_length,
        max_length=max_length,
        ge=ge,
        le=le,
        description=description,
        scopes=frozenset(scopes),
    )


@dataclass(frozen=True)
class EndpointSpec:
    """A single HTTP endpoint."""

    method: str
    path: str
    path_params: list[FieldSpec] = field(default_factory=list)
    query_params: list[FieldSpec] = field(default_factory=list)
    body_fields: list[FieldSpec] = field(default_factory=list)
    form_fields: list[FieldSpec] = field(default_factory=list)
    response_fields: list[FieldSpec] = field(default_factory=list)
    summary: str = ""
    description: str = ""


@dataclass(frozen=True)
class ResourceSpec:
    """One logical resource (e.g. "items") + its endpoints."""

    resource: str  # snake_case: "items"
    description: str = ""
    model_class: str = ""  # "Item"; auto-derived from resource if blank
    table_name: str = ""  # "items"; auto-derived from resource if blank
    tag: str = ""  # "items"; auto-derived
    endpoints: list[EndpointSpec] = field(default_factory=list)
    # Per-endpoint overrides for body / response fields, keyed by ``"METHOD path"``.
    # Use this when an endpoint has a different shape than the resource-level one.
    endpoint_overrides: dict[str, dict[str, list[FieldSpec]]] = field(default_factory=dict)

    def derived(self) -> ResourceSpec:
        """Return a copy with auto-derived fields populated."""
        resource = _safe_ident(self.resource, default="resource")
        model_class = self.model_class or _pascal(resource)
        table_name = self.table_name or resource
        tag = self.tag or resource
        return ResourceSpec(
            resource=resource,
            description=self.description or f"{model_class} resource",
            model_class=model_class,
            table_name=table_name,
            tag=tag,
            endpoints=list(self.endpoints),
            endpoint_overrides=dict(self.endpoint_overrides),
        )


# ---------------------------------------------------------------------------
# CodePlan + file model
# ---------------------------------------------------------------------------


_CREATE = "create"  # file does not exist; will be written
_MODIFY = "modify"  # file exists and content differs
_SKIP = "skip"  # file exists and is identical


@dataclass(frozen=True)
class GeneratedFile:
    """One file in the generated plan."""

    path: str  # relative to project root
    content: str
    kind: str = _CREATE
    existing_content: str | None = None  # populated when kind == "modify"
    template: str = ""  # which .tpl produced it (for UI labelling)


@dataclass
class CodePlan:
    """A plan that can be previewed and (optionally) applied."""

    plan_id: str
    resource: str
    summary: str
    files: list[GeneratedFile]
    created_at: float = field(default_factory=time.time)
    # Display data: list of endpoints that fed the plan.
    endpoints: list[EndpointSpec] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def creates(self) -> int:
        return sum(1 for f in self.files if f.kind == _CREATE)

    @property
    def modifies(self) -> int:
        return sum(1 for f in self.files if f.kind == _MODIFY)

    @property
    def skips(self) -> int:
        return sum(1 for f in self.files if f.kind == _SKIP)

    def is_noop(self) -> bool:
        return all(f.kind == _SKIP for f in self.files)


# ---------------------------------------------------------------------------
# Plan store
# ---------------------------------------------------------------------------


class _PlanStore:
    """In-memory plan store keyed by plan id (UUID4-like)."""

    def __init__(self) -> None:
        self._plans: dict[str, CodePlan] = {}
        self._ttls: dict[str, float] = {}

    def put(self, plan: CodePlan, *, ttl_seconds: int = 300) -> None:
        self._plans[plan.plan_id] = plan
        self._ttls[plan.plan_id] = time.time() + ttl_seconds

    def get(self, plan_id: str) -> CodePlan | None:
        self._gc()
        return self._plans.get(plan_id)

    def drop(self, plan_id: str) -> CodePlan | None:
        self._ttls.pop(plan_id, None)
        return self._plans.pop(plan_id, None)

    def _gc(self) -> None:
        now = time.time()
        expired = [pid for pid, exp in self._ttls.items() if exp < now]
        for pid in expired:
            self._plans.pop(pid, None)
            self._ttls.pop(pid, None)


_PLAN_STORE = _PlanStore()


def get_plan_store() -> _PlanStore:
    """Return the in-memory plan store (replaced in tests via :func:`set_plan_store`)."""
    return _PLAN_STORE


def set_plan_store(store: _PlanStore) -> None:
    """Swap the global plan store (intended for tests)."""
    global _PLAN_STORE
    _PLAN_STORE = store  # type: ignore[assignment]


def _new_plan_id() -> str:
    return hashlib.sha1(str(time.time_ns()).encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Form parsing
# ---------------------------------------------------------------------------


def parse_api_form(
    *,
    resource: str,
    description: str = "",
    fields_text: str,
) -> ResourceSpec:
    """Convert the admin form's text fields into a :class:`ResourceSpec`.

    The form has:

    * ``resource`` — the snake_case resource name (e.g. ``items``).
    * ``description`` — one-line description.
    * ``fields_text`` — one field per line, parsed by :func:`parse_field_line`.

    The form is intentionally minimal: every field line declares its scope via
    the trailing ``(scope, ...)`` annotation. The generator infers the
    necessary endpoints (list / get / create / update / delete) from the
    available fields:

    * If any field is in scope ``(body)`` or ``(form)`` → POST is added.
    * If any field is in scope ``(response)`` → GET list + GET single are added.
    * If the path has ``{id}`` style params → PATCH + DELETE are added.
    """
    resource = _safe_ident(resource, default="resource")
    fields: list[FieldSpec] = []
    errors: list[str] = []
    for n, line in enumerate(fields_text.splitlines(), start=1):
        if not line.strip() or line.strip().startswith("#"):
            continue
        try:
            fields.append(parse_field_line(line))
        except ValueError as exc:
            errors.append(f"line {n}: {exc}")

    if errors:
        raise ValueError("Invalid fields:\n  - " + "\n  - ".join(errors))

    if not fields:
        raise ValueError("At least one field is required")

    # Partition fields by scope.
    body_fields = [f for f in fields if f.has_scope("body")]
    form_fields = [f for f in fields if f.has_scope("form")]
    query_fields = [f for f in fields if f.has_scope("query")]
    path_fields = [f for f in fields if f.has_scope("path")]
    response_fields = [f for f in fields if f.has_scope("response")]
    model_fields = [f for f in fields if f.has_scope("model")]

    # If the user did not split the schema, treat every field as body + response.
    if not (body_fields or form_fields):
        body_fields = [f for f in fields if not f.has_scope("response", "query", "path")]
    if not response_fields:
        response_fields = body_fields

    # Synthesise the five canonical endpoints from the available fields.
    endpoints: list[EndpointSpec] = []

    # 1) GET list — uses query params (or none).
    endpoints.append(
        EndpointSpec(
            method="GET",
            path=f"/{resource}",
            query_params=query_fields,
            response_fields=response_fields,
            summary=f"List {resource}",
        )
    )

    # 2) GET single — only if we have a path param or a primary key in the schema.
    pk = _pick_primary_key(fields, resource)
    if pk is not None:
        endpoints.append(
            EndpointSpec(
                method="GET",
                path=f"/{resource}/{{{resource[:-1] if resource.endswith('s') and len(resource) > 1 else resource}_id}}",
                path_params=[pk],
                response_fields=response_fields,
                summary=f"Fetch a {resource[:-1] if resource.endswith('s') and len(resource) > 1 else resource}",
            )
        )

    # 3) POST — if there are body / form fields.
    if body_fields or form_fields:
        endpoints.append(
            EndpointSpec(
                method="POST",
                path=f"/{resource}",
                body_fields=body_fields,
                form_fields=form_fields,
                response_fields=response_fields,
                summary=f"Create a {resource[:-1] if resource.endswith('s') and len(resource) > 1 else resource}",
            )
        )

    # 4) PATCH + DELETE — only if we have a path param.
    if pk is not None:
        resource_id_name = pk.name
        # PATCH body: optional fields drawn from body_fields minus required ones.
        patch_body = [f for f in body_fields if not f.required]
        endpoints.append(
            EndpointSpec(
                method="PATCH",
                path=f"/{resource}/{{{resource_id_name}}}",
                path_params=[pk],
                body_fields=patch_body or body_fields,
                response_fields=response_fields,
                summary=f"Update a {resource[:-1] if resource.endswith('s') and len(resource) > 1 else resource}",
            )
        )
        endpoints.append(
            EndpointSpec(
                method="DELETE",
                path=f"/{resource}/{{{resource_id_name}}}",
                path_params=[pk],
                response_fields=[
                    FieldSpec(name=f"{resource_id_name}", py_type="int", required=True),
                    FieldSpec(name="deleted", py_type="bool", required=True, default="True"),
                ],
                summary=f"Delete a {resource[:-1] if resource.endswith('s') and len(resource) > 1 else resource}",
            )
        )

    # The "model" fields are all body + response + path + the standard
    # auto-fields (id, urn, created_at, updated_at, is_deleted).
    model_field_set = {f.name for f in model_fields}
    for f in body_fields + form_fields + path_fields:
        model_field_set.add(f.name)
    for f in response_fields:
        model_field_set.add(f.name)

    return ResourceSpec(
        resource=resource,
        description=description or "",
        endpoints=endpoints,
    ).derived()


def _pick_primary_key(fields: list[FieldSpec], resource: str) -> FieldSpec | None:
    """Pick a primary key field — usually ``<resource_singular>_id: int``. Returns
    ``None`` if no obvious candidate exists."""
    singular = resource[:-1] if resource.endswith("s") and len(resource) > 1 else resource
    expected = f"{singular}_id"
    for f in fields:
        if f.name == expected and f.has_scope("path"):
            return f
    # Look for any path-scoped field
    for f in fields:
        if f.has_scope("path"):
            return f
    return None


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------


_PYTHON_TYPE_TO_DEFAULTS: dict[str, tuple[str, str]] = {
    # py_type -> (ormx_field_call, default_py_literal)
    "str": ("StringField(max_length=200)", '""'),
    "int": ("Field(default=0)", "0"),
    "float": ("Field(default=0.0)", "0.0"),
    "bool": ("Field(default=False)", "False"),
    "datetime": ("Field(default=None)", "None"),
    "date": ("Field(default=None)", "None"),
    "time": ("Field(default=None)", "None"),
    "UUID": ("UUIDField(unique=True, default_factory=uuid4)", "uuid4()"),
    "bytes": ("Field(default=b'')", "b''"),
    "dict": ("Field(default=dict)", "dict"),
    "list": ("Field(default=list)", "list"),
}


def _model_field_line(f: FieldSpec) -> str:
    """Render a single ``field: type = default`` line for the model."""
    if f.py_type in _PYTHON_TYPE_TO_DEFAULTS:
        ormx_call, default_literal = _PYTHON_TYPE_TO_DEFAULTS[f.py_type]
    else:
        ormx_call = "Field(default=None)"
        default_literal = "None"
    if f.default is not None:
        default_literal = f.default
    return (
        f"    {f.name}: {f.py_type} = {ormx_call} if False else Field(default={default_literal})".replace(
            "if False else Field(default=", "= Field(default="
        )
        + (" ,default=" + f.default if f.default and f.default != default_literal else "")
    )


def _simple_model_field_line(f: FieldSpec) -> str:
    """Render a single ``field: type = Field(default=...)`` line for the model."""
    if f.py_type in _PYTHON_TYPE_TO_DEFAULTS:
        _, default_literal = _PYTHON_TYPE_TO_DEFAULTS[f.py_type]
    else:
        default_literal = "None"
    if f.default is not None:
        default_literal = f.default
    return f"    {f.name}: {f.py_type} = Field(default={default_literal})"


def _dto_field_kwargs(f: FieldSpec) -> str:
    """Render the keyword arguments for a ``Field(...)`` declaration in a DTO."""
    parts: list[str] = []
    if f.default is not None:
        parts.append(f"default={f.default}")
    if not f.required and f.default is None:
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
        pass  # type: ignore  # lazy circular
    if not parts:
        return ""
    return "=" + ", ".join(parts) if False else ", " + ", ".join(parts)  # type: ignore[unreachable]


def _dto_field_line(f: FieldSpec, *, include_default_none: bool = False) -> str:
    """Render ``name: type = Field(...)`` for a DTO field."""
    kwargs: list[str] = []
    if f.default is not None:
        kwargs.append(f"default={f.default}")
    elif not f.required and include_default_none:
        kwargs.append("default=None")
    if f.max_length is not None:
        kwargs.append(f"max_length={f.max_length}")
    if f.min_length is not None:
        kwargs.append(f"min_length={f.min_length}")
    if f.ge is not None:
        kwargs.append(f"ge={f.ge}")
    if f.le is not None:
        kwargs.append(f"le={f.le}")
    if f.description:
        kwargs.append(f'description="{f.description}"')
    if kwargs:
        return f"    {f.name}: {f.py_type} = Field({', '.join(kwargs)})"
    return f"    {f.name}: {f.py_type}"


def _request_class(name: str, fields: list[FieldSpec], *, partial: bool = False) -> str:
    body = "\n".join(_dto_field_line(f, include_default_none=partial) for f in fields)
    if not body:
        body = "    pass"
    return f'class {name}(IRequestDto):\n    """{name.replace("Request", " request").replace("DTO", "")}."""\n{body}\n'


def _response_class(name: str, fields: list[FieldSpec]) -> str:
    body = "\n".join(_dto_field_line(f, include_default_none=True) for f in fields)
    return f'class {name}(ApplicationBaseModel):\n    """{name.replace("Response", " response").replace("DTO", "")}."""\n{body}\n'


def _build_dtos(spec: ResourceSpec) -> dict[str, str]:
    """Build the request + response DTO file contents."""
    model_class = spec.model_class
    resource = spec.resource

    # Aggregate fields per DTO across the endpoints. We do this by walking the
    # endpoints and collecting fields by their role.
    body_create: list[FieldSpec] = []
    body_update: list[FieldSpec] = []
    query_list: list[FieldSpec] = []
    response_single: list[FieldSpec] = []
    seen: set[str] = set()

    for ep in spec.endpoints:
        for f in ep.body_fields + ep.form_fields:
            if ep.method == "PATCH" and f.name not in seen:
                body_update.append(f)
            elif f.name not in seen:
                body_create.append(f)
            seen.add(f.name)
        for f in ep.query_params:
            if f.name not in seen:
                query_list.append(f)
            seen.add(f.name)
        if ep.method in {"GET", "POST", "PATCH"} and ep.response_fields:
            for f in ep.response_fields:
                if f.name not in seen:
                    response_single.append(f)
                    seen.add(f.name)

    # List response: clone the single-response fields plus pagination.
    # (Used by the renderer below; tracked here for clarity.)

    # If we never saw any response fields, fall back to id+urn+created_at+updated_at
    if not response_single:
        response_single = [
            FieldSpec(name="id", py_type="int", required=True),
            FieldSpec(name="urn", py_type="UUID", required=True),
            FieldSpec(name="created_at", py_type="datetime", required=False, default="None"),
            FieldSpec(name="updated_at", py_type="datetime", required=False, default="None"),
        ]

    # Request DTOs
    request_classes: list[str] = []
    request_exports: list[str] = []
    if body_create:
        request_classes.append(_request_class(f"Create{model_class}Request", body_create))
        request_exports.append(f'    "Create{model_class}Request",')
    if body_update or any(ep.method == "PATCH" for ep in spec.endpoints):
        if not body_update:
            body_update = list(body_create)
        request_classes.append(
            _request_class(f"Update{model_class}Request", body_update, partial=True)
        )
        request_exports.append(f'    "Update{model_class}Request",')
    if query_list or any(ep.method == "GET" and ep.path == f"/{resource}" for ep in spec.endpoints):
        if not query_list:
            query_list = [
                FieldSpec(name="offset", py_type="int", required=True, default="0", ge=0),
                FieldSpec(name="limit", py_type="int", required=True, default="50", ge=1, le=200),
            ]
        # Convention: List{model_class}sRequest (plural), matching the
        # existing mvc/ template's `ListItemsRequest` naming.
        list_request_name = f"List{model_class}sRequest"
        request_classes.append(_request_class(list_request_name, query_list, partial=True))
        request_exports.append(f'    "{list_request_name}",')

    # Always have Get/Delete requests for the path-param endpoint.
    singular = resource[:-1] if resource.endswith("s") and len(resource) > 1 else resource
    request_classes.append(
        _request_class(
            f"Get{model_class}Request",
            [FieldSpec(name=f"{singular}_id", py_type="int", required=True, ge=1)],
        )
    )
    request_classes.append(
        _request_class(
            f"Delete{model_class}Request",
            [FieldSpec(name=f"{singular}_id", py_type="int", required=True, ge=1)],
        )
    )
    request_exports.append(f'    "Get{model_class}Request",')
    request_exports.append(f'    "Delete{model_class}Request",')

    # Response DTOs
    response_classes = [
        _response_class(f"{model_class}Response", response_single),
        _response_class(
            f"List{model_class}Response",
            [
                FieldSpec(name="items", py_type=f"list[{model_class}Response]", required=True),
                FieldSpec(name="total", py_type="int", required=True),
                FieldSpec(name="offset", py_type="int", required=True),
                FieldSpec(name="limit", py_type="int", required=True),
            ],
        ),
    ]
    if any(ep.method == "POST" for ep in spec.endpoints):
        response_classes.insert(
            0,
            _response_class(
                f"Create{model_class}Response",
                [
                    FieldSpec(name="id", py_type="int", required=True),
                    FieldSpec(name="urn", py_type="UUID", required=True),
                ]
                + [f for f in response_single if f.name not in {"id", "urn"}],
            ),
        )
    if any(ep.method == "PATCH" for ep in spec.endpoints):
        response_classes.insert(
            0,
            _response_class(
                f"Update{model_class}Response",
                response_single,
            ),
        )
    if any(ep.method == "DELETE" for ep in spec.endpoints):
        response_classes.insert(
            0,
            _response_class(
                f"Delete{model_class}Response",
                [
                    FieldSpec(name=f"{singular}_id", py_type="int", required=True),
                    FieldSpec(name="deleted", py_type="bool", required=True, default="True"),
                ],
            ),
        )

    requests = _render_template(
        "dto_requests.py.tpl",
        request_classes="\n\n".join(request_classes) if request_classes else "    pass",
        request_exports="\n".join(request_exports) if request_exports else "",
    )
    responses = _render_template(
        "dto_responses.py.tpl",
        response_classes="\n\n".join(response_classes),
    )
    return {
        "requests": requests,
        "responses": responses,
    }


def _build_model(spec: ResourceSpec) -> str:
    """Build the model file content."""
    model_class = spec.model_class
    # Collect model fields: union of body, form, response, path fields + standard
    seen: set[str] = set()
    model_fields: list[FieldSpec] = []
    for ep in spec.endpoints:
        for f in ep.body_fields + ep.form_fields + ep.response_fields + ep.path_params:
            if f.name not in seen and f.name not in {
                "id",
                "urn",
                "created_at",
                "updated_at",
                "is_deleted",
            }:
                model_fields.append(f)
                seen.add(f.name)
    if not model_fields:
        # Fall back to a single `name: str` field if the user provided none.
        model_fields = [FieldSpec(name="name", py_type="str", required=True, max_length=200)]
    fields_text = "\n".join(_simple_model_field_line(f) for f in model_fields)
    return _render_template(
        "model.py.tpl",
        model_class=model_class,
        description=spec.description or f"{model_class} resource",
        table_name=spec.table_name,
        resource=spec.resource,
        model_fields=fields_text,
    )


def _build_mapper(spec: ResourceSpec) -> str:
    model_class = spec.model_class
    resource = spec.resource
    # Collect the fields that go into a response.
    seen: set[str] = set()
    fields: list[FieldSpec] = []
    for ep in spec.endpoints:
        for f in ep.response_fields:
            if f.name not in seen and f.name not in {"id", "urn"}:
                fields.append(f)
                seen.add(f.name)
    if not fields:
        fields = [FieldSpec(name="name", py_type="str", required=True, max_length=200)]
    mapping = (
        "".join(f"        {f.name}={f.name},\n" for f in fields).rstrip("\n")
        or "        # no extra fields"
    )
    return _render_template(
        "mapper.py.tpl",
        model_class=model_class,
        resource=resource,
        response_mapping_fields=mapping,
    )


def _build_services(spec: ResourceSpec) -> dict[str, str]:
    """Build the 5 service files + __init__."""
    model_class = spec.model_class
    resource = spec.resource
    # Variable name for the repo: prefer the singular form to match the model.
    singular = resource[:-1] if resource.endswith("s") and len(resource) > 1 else resource
    repo_var = f"{singular}_repo"
    resource_upper = resource.upper()

    # Collect the response fields once for re-use in service code.
    seen: set[str] = set()
    response_fields: list[FieldSpec] = []
    for ep in spec.endpoints:
        for f in ep.response_fields:
            if f.name not in seen and f.name not in {"id", "urn"}:
                response_fields.append(f)
                seen.add(f.name)
    if not response_fields:
        response_fields = [FieldSpec(name="name", py_type="str", required=True, max_length=200)]

    response_args = "".join(
        f"            {f.name}=saved.{f.name},\n" for f in response_fields
    ).rstrip("\n")

    # init_fields for create service: body_fields + form_fields
    init_fields: list[FieldSpec] = []
    seen = set()
    for ep in spec.endpoints:
        if ep.method == "POST":
            for f in ep.body_fields + ep.form_fields:
                if f.name not in seen:
                    init_fields.append(f)
                    seen.add(f.name)
    init_args = (
        "".join(f"            {f.name}=request.{f.name},\n" for f in init_fields).rstrip("\n")
        or "            # no fields"
    )

    # update_fields for update service: body_fields with `is not None` guards
    seen = set()
    update_fields: list[FieldSpec] = []
    for ep in spec.endpoints:
        if ep.method == "PATCH":
            for f in ep.body_fields:
                if f.name not in seen:
                    update_fields.append(f)
                    seen.add(f.name)
    update_args = (
        "\n".join(
            f"        if request.{f.name} is not None:\n            item.{f.name} = request.{f.name}"
            for f in update_fields
        )
        or "        # no fields to update"
    )

    files: dict[str, str] = {}
    files["create"] = _render_template(
        "service_create.py.tpl",
        resource=resource,
        resource_upper=resource_upper,
        model_class=model_class,
        repo_var=repo_var,
        init_fields=init_args,
        response_fields=response_args,
    )
    files["get"] = _render_template(
        "service_get.py.tpl",
        resource=resource,
        resource_upper=resource_upper,
        model_class=model_class,
        repo_var=repo_var,
        response_fields=response_args,
    )
    files["list"] = _render_template(
        "service_list.py.tpl",
        resource=resource,
        resource_upper=resource_upper,
        model_class=model_class,
        repo_var=repo_var,
    )
    files["update"] = _render_template(
        "service_update.py.tpl",
        resource=resource,
        resource_upper=resource_upper,
        model_class=model_class,
        repo_var=repo_var,
        update_fields=update_args,
        response_fields=response_args,
    )
    files["delete"] = _render_template(
        "service_delete.py.tpl",
        resource=resource,
        resource_upper=resource_upper,
        model_class=model_class,
        repo_var=repo_var,
    )
    files["__init__"] = _render_template(
        "services_init.py.tpl",
        resource=resource,
        model_class=model_class,
    )
    return files


def _build_controller(spec: ResourceSpec) -> str:
    model_class = spec.model_class
    resource = spec.resource
    singular = resource[:-1] if resource.endswith("s") and len(resource) > 1 else resource
    path_param = f"{singular}_id"
    resource_upper = resource.upper()

    dto_imports = ",\n".join(
        [
            f"    Create{model_class}Request",
            f"    Update{model_class}Request",
            f"    Get{model_class}Request",
            f"    Delete{model_class}Request",
            f"    List{model_class}sRequest",
        ]
    )
    service_imports = ",\n".join(
        [
            f"    Create{model_class}Service",
            f"    Get{model_class}Service",
            f"    List{model_class}sService",
            f"    Update{model_class}Service",
            f"    Delete{model_class}Service",
        ]
    )

    # request_build_fields for PATCH handler: only optional fields
    seen: set[str] = set()
    patch_fields: list[FieldSpec] = []
    for ep in spec.endpoints:
        if ep.method == "PATCH":
            for f in ep.body_fields:
                if f.name not in seen:
                    patch_fields.append(f)
                    seen.add(f.name)
    request_build = (
        "".join(f"            {f.name}=payload.{f.name},\n" for f in patch_fields).rstrip("\n")
        or "            # no fields"
    )

    return _render_template(
        "controller.py.tpl",
        resource=resource,
        resource_upper=resource_upper,
        model_class=model_class,
        singular=singular,
        path_param=path_param,
        dto_imports=dto_imports,
        service_imports=service_imports,
        request_build_fields=request_build,
    )





def _build_controller_marshmallow(spec: ResourceSpec) -> str:
    """Render the controller for the Marshmallow backend (no Pydantic)."""
    model_class = spec.model_class
    resource = spec.resource
    singular = resource[:-1] if resource.endswith("s") and len(resource) > 1 else resource
    path_param = f"{singular}_id"
    resource_upper = resource.upper()

    # Schemas to import from dtos.<resource>.schemas (the generated file).
    marshmallow_imports = ",\n".join(
        [
            f"    create_{resource}_request_schema",
            f"    update_{resource}_request_schema",
            f"    get_{resource}_request_schema",
            f"    delete_{resource}_request_schema",
            f"    list_{resource}s_request_schema",
        ]
    )
    service_imports = ",\n".join(
        [
            f"    Create{model_class}Service",
            f"    Get{model_class}Service",
            f"    List{model_class}sService",
            f"    Update{model_class}Service",
            f"    Delete{model_class}Service",
        ]
    )

    return _render_template(
        "controller_marshmallow.py.tpl",
        resource=resource,
        resource_upper=resource_upper,
        model_class=model_class,
        singular=singular,
        path_param=path_param,
        marshmallow_imports=marshmallow_imports,
        service_imports=service_imports,
    )


def _build_dependency(spec: ResourceSpec) -> str:
    return _render_template(
        "dependency.py.tpl",
        resource=spec.resource,
        model_class=spec.model_class,
    )


def _build_dtos_init(spec: ResourceSpec) -> str:
    """Build the dtos/<resource>/__init__.py aggregating request/response DTOs."""
    model_class = spec.model_class
    # Collect all request DTOs by scanning endpoints.
    reqs: list[str] = []
    resps: list[str] = []

    if any(ep.method == "POST" for ep in spec.endpoints):
        reqs.append(f"Create{model_class}Request")
    if any(ep.method == "PATCH" for ep in spec.endpoints):
        reqs.append(f"Update{model_class}Request")
    if any(ep.method == "GET" and not ep.path_params for ep in spec.endpoints):
        reqs.append(f"List{model_class}Request")
    if any(ep.method == "GET" and ep.path_params for ep in spec.endpoints):
        reqs.append(f"Get{model_class}Request")
    if any(ep.method == "DELETE" for ep in spec.endpoints):
        reqs.append(f"Delete{model_class}Request")

    if any(ep.method == "POST" for ep in spec.endpoints):
        resps.append(f"Create{model_class}Response")
    if any(ep.method == "PATCH" for ep in spec.endpoints):
        resps.append(f"Update{model_class}Response")
    if any(ep.method == "GET" and ep.path_params for ep in spec.endpoints):
        resps.append(f"{model_class}Response")
    if any(ep.method == "GET" and not ep.path_params for ep in spec.endpoints):
        resps.append(f"List{model_class}Response")
    if any(ep.method == "DELETE" for ep in spec.endpoints):
        resps.append(f"Delete{model_class}Response")

    all_lines = [f'    "{r}",' for r in reqs] + [f'    "{r}",' for r in resps]
    return _render_template(
        "dtos_init.py.tpl",
        resource=spec.resource,
        request_exports="\n".join(f"    {r}," for r in reqs),
        response_exports="\n".join(f"    {r}," for r in resps),
        all_exports="\n".join(all_lines),
    )


def _build_migration(spec: ResourceSpec) -> str:
    model_class = spec.model_class
    table_name = spec.table_name
    # Collect column types.
    seen: set[str] = set()
    columns: list[tuple[str, str]] = []  # (column_type, column_name)
    for ep in spec.endpoints:
        for f in ep.body_fields + ep.form_fields + ep.response_fields + ep.path_params:
            if f.name in seen:
                continue
            seen.add(f.name)
            col = _sql_column(f)
            if col:
                columns.append(col)
    if not columns:
        columns.append(("VARCHAR(200)", "name"))
    migration_columns = "\n".join(f"    {col}     NOT NULL," for col, _ in columns)
    return _render_template(
        "migration.sql.tpl",
        model_class=model_class,
        table_name=table_name,
        migration_columns=migration_columns,
    )


def _sql_column(f: FieldSpec) -> tuple[str, str] | None:
    """Return the SQL column type + name for a model field. ``None`` for auto-managed fields."""
    if f.name in {"id", "urn", "created_at", "updated_at", "is_deleted"}:
        return None
    mapping = {
        "str": ("VARCHAR(200)", f.name),
        "int": ("INTEGER", f.name),
        "float": ("DOUBLE PRECISION", f.name),
        "bool": ("BOOLEAN", f.name),
        "datetime": ("TIMESTAMPTZ", f.name),
        "date": ("DATE", f.name),
        "time": ("TIME", f.name),
        "UUID": ("UUID", f.name),
        "bytes": ("BYTEA", f.name),
        "dict": ("JSONB", f.name),
    }
    return mapping.get(f.py_type, ("JSONB", f.name))


def _build_test(spec: ResourceSpec) -> str:
    """Build a minimal pytest for the DTOs."""
    resource = spec.resource
    model_class = spec.model_class
    # Pull the first required body field to test "validation rejects empty".
    seen: set[str] = set()
    first_required: FieldSpec | None = None
    for ep in spec.endpoints:
        for f in ep.body_fields:
            if f.name not in seen:
                if not first_required:
                    first_required = f
                seen.add(f.name)
    if first_required is None:
        # Default test: just import the request module.
        return _render_template(
            "test.py.tpl",
            resource=resource,
            model_class=model_class,
            request_test_imports="",
        )
    return _render_template(
        "test.py.tpl",
        resource=resource,
        model_class=model_class,
        request_test_imports="",
    )


# ---------------------------------------------------------------------------
# Plan builder
# ---------------------------------------------------------------------------


def generate_resource(
    spec: ResourceSpec,
    *,
    project_root: Path,
    schema: str = "pydantic",
) -> CodePlan:
    """Build a :class:`CodePlan` for *spec* relative to *project_root*.

    *schema* selects the DTO backend — ``"pydantic"`` (default) or
    ``"marshmallow"``. See :mod:`rivex_codegen._schemas` for the supported
    set and what each backend emits.
    """
    # The codegen module is routinely loaded by tests via importlib.util
    # without the full Rivex package being importable. We try the
    # package-relative import first and fall back to loading the file
    # directly so the codegen remains test-isolated.
    import importlib.util as _ilu
    import sys as _sys
    from pathlib import Path as _P

    _codegen_schemas = _sys.modules.get("rivex_codegen._schemas")
    if _codegen_schemas is None:
        try:
            from rivex_codegen import _schemas as _codegen_schemas  # type: ignore[import-not-found]
        except ImportError:
            if __package__:
                try:
                    from . import _schemas as _codegen_schemas  # type: ignore[no-redef]
                except ImportError:
                    _codegen_schemas = None
        if _codegen_schemas is None:
            # Last-ditch: load the file directly (test isolation).
            _spec = _ilu.spec_from_file_location(
                "rivex_codegen_schemas_under_test",
                _P(__file__).resolve().parent / "_schemas.py",
            )
            assert _spec is not None and _spec.loader is not None
            _codegen_schemas = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_codegen_schemas)
    schema_files = _codegen_schemas.render_for_backend(spec, backend=schema)
    plan = CodePlan(
        plan_id=_new_plan_id(),
        resource=spec.resource,
        summary=_summarise_spec(spec),
        files=[],
        endpoints=list(spec.endpoints),
    )

    # Build every file and tag it with kind.
    built: list[tuple[str, str, str]] = []  # (rel_path, content, template_name)

    # 1) Model
    built.append(
        (
            f"models/{spec.resource}.py",
            _build_model(spec),
            "model.py.tpl",
        )
    )

    # 2) Repository
    built.append(
        (
            f"repositories/{spec.resource}.py",
            _render_template(
                "repository.py.tpl", resource=spec.resource, model_class=spec.model_class
            ),
            "repository.py.tpl",
        )
    )

    # 3) DTOs + (optional) backend-specific files. Each backend emits
    # native code with no Pydantic shortcuts — the controller is
    # backend-specific (see the controller templates).
    schema_files = _codegen_schemas.render_for_backend(spec, backend=schema)

    # Backend-specific notes for the preview.
    if "marshmallow_schemas" in schema_files:
        plan.notes.append(
            "Install `marshmallow` to use the generated Schema classes: `pip install marshmallow`."
        )

    # The Pydantic backend emits a single ``dtos/<resource>/requests.py``
    # with both request and response models in one file. Other backends
    # have their own structure (Marshmallow: schemas.py + request-only file).
    if schema == "pydantic":
        built.append(
            (
                f"dtos/{spec.resource}/requests.py",
                schema_files["dtos"],
                "pydantic/requests.py.tpl",
            )
        )
    elif schema == "marshmallow":
        # The marshmallow backend does not emit a separate request module —
        # the Schema classes in ``dtos/<resource>/schemas.py`` double as the
        # DTOs (the controller calls ``.load(body)`` directly).
        built.append(
            (
                f"dtos/{spec.resource}/schemas.py",
                schema_files["marshmallow_schemas"],
                "marshmallow/schemas.py.tpl",
            )
        )
        built.append(
            (
                f"dtos/{spec.resource}/__init__.py",
                '"""{resource} DTO module."""\n',
                "marshmallow/__init__.py.tpl",
            )
        )
    # 4) Mapper
    built.append(
        (
            f"mappers/{spec.resource}_mapper.py",
            _build_mapper(spec),
            "mapper.py.tpl",
        )
    )

    # 5) Services
    services = _build_services(spec)
    for name, content in services.items():
        if name == "__init__":
            built.append(
                (
                    f"services/{spec.resource}/__init__.py",
                    content,
                    "services_init.py.tpl",
                )
            )
        else:
            built.append(
                (
                    f"services/{spec.resource}/{name}_{spec.resource}.py"
                    if name in {"create", "get", "update", "delete"}
                    else f"services/{spec.resource}/{name}_{spec.resource}.py",
                    content,
                    f"service_{name}.py.tpl",
                )
            )

    # 6) Controller — choose the right template per backend.
    controller_template = {
        "pydantic": "controller.py.tpl",
        "marshmallow": "controller_marshmallow.py.tpl",
    }[schema]
    if schema == "pydantic":
        controller_content = _build_controller(spec)
    else:  # marshmallow
        controller_content = _build_controller_marshmallow(spec)
    built.append(
        (
            f"controllers/{spec.resource}/{spec.resource}_controller.py",
            controller_content,
            controller_template,
        )
    )
    built.append(
        (
            f"controllers/{spec.resource}/__init__.py",
            f'"""{spec.resource} controllers."""\nfrom controllers.{spec.resource}.{spec.resource}_controller import {spec.model_class}sController\n\n__all__ = ["{spec.model_class}sController"]\n',
            "controllers_init.py.tpl",
        )
    )

    # 7) DI
    built.append(
        (
            f"dependencies/services/{spec.resource}_service.py",
            _build_dependency(spec),
            "dependency.py.tpl",
        )
    )

    # 8) Migration
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    built.append(
        (
            f"migrations/{ts}_{spec.table_name}.sql",
            _build_migration(spec),
            "migration.sql.tpl",
        )
    )

    # 9) Test
    built.append(
        (
            f"tests/test_{spec.resource}.py",
            _build_test(spec),
            "test.py.tpl",
        )
    )

    # Tag each file with kind.
    for rel, content, tpl in built:
        kind, existing = _classify(project_root / rel, content)
        plan.files.append(
            GeneratedFile(
                path=rel,
                content=content,
                kind=kind,
                existing_content=existing,
                template=tpl,
            )
        )

    plan.notes = _build_notes(spec)
    return plan


def _classify(target: Path, new_content: str) -> tuple[str, str | None]:
    """Return (kind, existing_content). ``kind`` is create / modify / skip."""
    if not target.exists():
        return _CREATE, None
    try:
        existing = target.read_text(encoding="utf-8")
    except OSError:
        return _CREATE, None
    if existing == new_content:
        return _SKIP, existing
    return _MODIFY, existing


def _summarise_spec(spec: ResourceSpec) -> str:
    methods = sorted({ep.method for ep in spec.endpoints})
    return f"{spec.resource}: {len(spec.endpoints)} endpoints ({', '.join(methods)})"


def _build_notes(spec: ResourceSpec) -> list[str]:
    notes: list[str] = []
    notes.append(
        f"Add `from controllers.{spec.resource}.{spec.resource}_controller import {spec.model_class}sController` "
        "to `controllers/__init__.py` so the new controller is registered."
    )
    notes.append(
        f"Add `from models.{spec.resource} import {spec.model_class}` to `models/__init__.py` so the "
        "ORM model registry picks up the new table."
    )
    notes.append("Run `ormx migrate --models models --dir migrations` to apply the new migration.")
    return notes


# ---------------------------------------------------------------------------
# Apply + plan lifecycle
# ---------------------------------------------------------------------------


class CodegenError(RuntimeError):
    """Raised when a plan cannot be applied (e.g. unsafe path)."""


def apply_plan(plan: CodePlan, *, project_root: Path) -> list[str]:
    """Write every file in *plan* under *project_root*.

    Returns the list of files that were actually written (skips are not
    written, modifies overwrite the previous content).

    Raises :class:`CodegenError` if any path would escape *project_root*.
    """
    project_root = project_root.resolve()
    written: list[str] = []
    for f in plan.files:
        target = (project_root / f.path).resolve()
        if not _is_within(target, project_root):
            raise CodegenError(f"refusing to write outside project root: {f.path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.content, encoding="utf-8")
        written.append(str(target.relative_to(project_root)))
    return written


def _is_within(path: Path, root: Path) -> bool:
    """Return True if *path* is inside *root* (after resolving)."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _render_template(name: str, **context: Any) -> str:
    """Read a template from :data:`TEMPLATES_DIR` and substitute placeholders."""
    path = TEMPLATES_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Template not found: {name}")
    raw = path.read_text(encoding="utf-8")
    return _PLACEHOLDER_RE.sub(lambda m: str(context.get(m.group(1), m.group(0))), raw)


def _safe_ident(value: str, *, default: str = "resource") -> str:
    """Sanitise a user-typed resource name to a valid Python identifier."""
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip().lower()).strip("_")
    if not cleaned or cleaned[0].isdigit():
        return default
    return cleaned


def _pascal(value: str) -> str:
    """snake_case -> PascalCase, with a sensible singular form for plurals."""
    singular = value[:-1] if value.endswith("s") and len(value) > 1 else value
    return "".join(part.capitalize() for part in singular.split("_") if part)


# ---------------------------------------------------------------------------
# Preview HTML rendering
# ---------------------------------------------------------------------------


_PLAIN_TEMPLATE = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Preview</title>
<style>
body {{ font-family: var(--mono); font-size: 12px; background: #fafafa; color: #111; margin: 0; padding: 16px; white-space: pre; }}
.added {{ background: #e6ffec; color: #0a5d2c; }}
.removed {{ background: #ffeef0; color: #8a1f2c; }}
.context {{ color: #6b6b6b; }}
</style></head>
<body>{body}</body></html>
"""


def plan_to_preview_html(plan: CodePlan) -> str:
    """Render the entire plan as one big HTML page (syntax-highlighted diff)."""
    from html import escape

    chunks: list[str] = []
    for f in plan.files:
        header = (
            f'<div style="font-family: var(--sans); font-size: 13px; font-weight: 700; '
            f'margin: 24px 0 4px; padding: 8px 12px; background: var(--soft); border-radius: 6px;">'
            f"{_kind_badge(f.kind)} {escape(f.path)} "
            f'<span style="color: var(--muted); font-weight: 400; font-size: 11px;">'
            f"({len(f.content):,} chars · from {escape(f.template)})</span>"
            f"</div>"
        )
        chunks.append(header)
        if f.kind == _SKIP:
            chunks.append(
                '<p style="color: var(--muted); font-size: 12px; margin: 4px 12px 16px;">'
                "No changes — file already up to date."
                "</p>"
            )
            continue
        if f.kind == _MODIFY and f.existing_content is not None:
            diff_html = _render_diff_html(f.existing_content, f.content)
        else:
            diff_html = _render_plain_html(f.content, cls="added")
        chunks.append(
            f'<pre style="background: #fafafa; padding: 14px 16px; border-radius: 6px; '
            f'overflow: auto; max-height: 480px; font-size: 12px; line-height: 1.5;">'
            f"{diff_html}</pre>"
        )
    return "".join(chunks)


def _kind_badge(kind: str) -> str:
    label = {"create": "+ NEW", "modify": "~ MOD", "skip": "= SKIP"}.get(kind, kind)
    color = {"create": "var(--green)", "modify": "var(--blue)", "skip": "var(--muted)"}.get(
        kind, "var(--fg)"
    )
    return (
        f'<span style="font-family: var(--mono); font-size: 10px; padding: 2px 6px; '
        f'background: {color}; color: white; border-radius: 3px; margin-right: 6px;">{label}</span>'
    )


def _render_diff_html(old: str, new: str) -> str:
    """Render a unified diff with per-line CSS classes."""
    from html import escape

    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        lineterm="",
        n=2,
    )
    out: list[str] = []
    for line in diff:
        text = line.rstrip("\n")
        if text.startswith("+++") or text.startswith("---"):
            continue
        if text.startswith("@@"):
            cls = "context"
        elif text.startswith("+"):
            cls = "added"
        elif text.startswith("-"):
            cls = "removed"
        else:
            cls = "context"
        out.append(f'<span class="{cls}">{escape(text)}</span>')
    return "\n".join(out) if out else _render_plain_html(new, cls="added")


def _render_plain_html(text: str, *, cls: str = "added") -> str:
    from html import escape

    return "\n".join(
        f'<span class="{cls}">{escape(line) if line else "&nbsp;"}</span>'
        for line in text.splitlines()
    )


def plan_to_summary(plan: CodePlan) -> str:
    """One-line summary used in the dashboard banner."""
    bits: list[str] = []
    if plan.creates:
        bits.append(f"{plan.creates} new")
    if plan.modifies:
        bits.append(f"{plan.modifies} modified")
    if plan.skips:
        bits.append(f"{plan.skips} unchanged")
    return ", ".join(bits) or "no changes"


__all__ = [
    "TEMPLATES_DIR",
    "CodegenError",
    "CodePlan",
    "EndpointSpec",
    "FieldSpec",
    "GeneratedFile",
    "ResourceSpec",
    "apply_plan",
    "generate_resource",
    "get_plan_store",
    "parse_api_form",
    "parse_field_line",
    "plan_to_preview_html",
    "plan_to_summary",
    "set_plan_store",
]
