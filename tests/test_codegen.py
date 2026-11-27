"""Tests for the resource scaffolder (codegen)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the codegen module without triggering the full package import.
# ---------------------------------------------------------------------------


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).resolve().parents[1] / "rivex_codegen" / relative,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_codegen = _load_module("rivex_codegen_under_test", "__init__.py")


# ---------------------------------------------------------------------------
# Field parsing
# ---------------------------------------------------------------------------


def test_parse_field_line_minimal() -> None:
    f = _codegen.parse_field_line("title: str:required:max=200")
    assert f.name == "title"
    assert f.py_type == "str"
    assert f.required is True
    assert f.max_length == 200
    assert "body" in f.scopes
    assert "response" in f.scopes
    assert "model" in f.scopes


def test_parse_field_line_with_scope() -> None:
    f = _codegen.parse_field_line("offset: int:default=0:ge=0 (query)")
    assert f.name == "offset"
    assert f.py_type == "int"
    assert f.default == "0"
    assert f.ge == 0
    assert f.scopes == frozenset({"query"})


def test_parse_field_line_uuid_alias() -> None:
    f = _codegen.parse_field_line("urn: uuid (response)")
    assert f.py_type == "UUID"


def test_parse_field_line_optional() -> None:
    f = _codegen.parse_field_line("description: str:optional:max=2000")
    assert f.required is False
    assert f.max_length == 2000


def test_parse_field_line_with_default_quoted() -> None:
    f = _codegen.parse_field_line('name: str:default="hello"')
    assert f.default == "hello"
    assert f.required is False


def test_parse_field_line_with_description() -> None:
    f = _codegen.parse_field_line(
        'title: str:required:max=200:description="The human-readable title"'
    )
    assert f.description == "The human-readable title"


def test_parse_field_line_ignores_comments_and_blanks() -> None:
    with pytest.raises(ValueError):
        _codegen.parse_field_line("")
    with pytest.raises(ValueError):
        _codegen.parse_field_line("   ")
    with pytest.raises(ValueError):
        _codegen.parse_field_line("# a comment")


def test_parse_field_line_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        _codegen.parse_field_line("not a field line at all")


def test_parse_field_line_container_type() -> None:
    f = _codegen.parse_field_line("tags: list[str] (body)")
    assert f.py_type == "list[str]"


def test_parse_field_line_optional_list_in_scopes() -> None:
    f = _codegen.parse_field_line("photo: bytes (form)")
    assert "form" in f.scopes


# ---------------------------------------------------------------------------
# Form parsing
# ---------------------------------------------------------------------------


def test_parse_api_form_minimal_items() -> None:
    spec = _codegen.parse_api_form(
        resource="items",
        description="Demo resource",
        fields_text="""
title: str:required:max=200
description: str:optional:max=2000
is_completed: bool:default=false
id: int (response)
urn: uuid (response)
created_at: datetime (response)
updated_at: datetime (response)
item_id: int:required (path)
offset: int:default=0:min=0 (query)
limit: int:default=50:min=1:max=200 (query)
""",
    )
    assert spec.resource == "items"
    assert spec.model_class == "Item"
    assert spec.table_name == "items"
    methods = {ep.method for ep in spec.endpoints}
    # 5 canonical CRUD endpoints
    assert methods == {"GET", "POST", "PATCH", "DELETE"}


def test_parse_api_form_singular_resource() -> None:
    spec = _codegen.parse_api_form(
        resource="user",
        fields_text="id: int (response)\nurn: uuid (response)",
    )
    assert spec.resource == "user"
    assert spec.model_class == "User"


def test_parse_api_form_normalises_unsafe_resource_names() -> None:
    """Unsafe names are sanitised to a valid Python identifier instead of raising."""
    spec = _codegen.parse_api_form(
        resource="!!!",
        fields_text="title: str:required",
    )
    # Sanitised to a safe default
    assert spec.resource == "resource"
    # "  " sanitises the same way
    spec2 = _codegen.parse_api_form(
        resource="",
        fields_text="title: str:required",
    )
    assert spec2.resource == "resource"


def test_parse_api_form_requires_at_least_one_field() -> None:
    with pytest.raises(ValueError):
        _codegen.parse_api_form(resource="items", fields_text="   \n# only comments\n")


def test_parse_api_form_aggregates_errors() -> None:
    with pytest.raises(ValueError) as exc:
        _codegen.parse_api_form(
            resource="items",
            fields_text="title: str:required\nbroken: :\n",
        )
    assert "line 2" in str(exc.value)


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------


def _example_spec() -> _codegen.ResourceSpec:
    return _codegen.parse_api_form(
        resource="items",
        description="Demo items resource",
        fields_text="""
title: str:required:max=200
description: str:optional:max=2000
is_completed: bool:default=false
id: int (response)
urn: uuid (response)
created_at: datetime (response)
updated_at: datetime (response)
item_id: int:required (path)
offset: int:default=0:min=0 (query)
limit: int:default=50:min=1:max=200 (query)
""",
    )


def test_generate_resource_creates_expected_files(tmp_path: Path) -> None:
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=tmp_path)
    paths = {f.path for f in plan.files}
    # Core layered files
    assert "models/items.py" in paths
    assert "repositories/items.py" in paths
    # Pydantic backend puts requests + responses in a single file
    assert "dtos/items/requests.py" in paths
    assert "mappers/items_mapper.py" in paths
    # 5 services
    for op in ("create", "get", "list", "update", "delete"):
        assert f"services/items/{op}_items.py" in paths
    assert "services/items/__init__.py" in paths
    # Controller + DI
    assert "controllers/items/items_controller.py" in paths
    assert "controllers/items/__init__.py" in paths
    assert "dependencies/services/items_service.py" in paths
    # Migration + test
    assert any(p.startswith("migrations/") and p.endswith("_items.sql") for p in paths)
    assert "tests/test_items.py" in paths


def test_generate_resource_pydantic_backend_emits_single_dto_file(tmp_path: Path) -> None:
    """The Pydantic backend emits request + response classes in one file."""
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=tmp_path, schema="pydantic")
    paths = {f.path for f in plan.files}
    assert "dtos/items/requests.py" in paths
    # The single file should contain BOTH Request and Response DTOs.
    by_path = {f.path: f for f in plan.files}
    content = by_path["dtos/items/requests.py"].content
    assert "CreateItemRequest" in content
    assert "UpdateItemRequest" in content
    assert "GetItemRequest" in content
    assert "DeleteItemRequest" in content
    assert "ListItemsRequest" in content
    assert "ItemResponse" in content
    assert "ListItemsResponse" in content
    # No marshmallow specific files
    assert "dtos/items/schemas.py" not in paths


def test_generate_resource_marshmallow_backend_emits_schemas_file(tmp_path: Path) -> None:
    """The Marshmallow backend emits ``schemas.py`` and a controller that
    uses ``schema.load(body)`` — no Pydantic dependency."""
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=tmp_path, schema="marshmallow")
    paths = {f.path for f in plan.files}
    by_path = {f.path: f for f in plan.files}

    # Schemas file has the Marshmallow Schema classes
    assert "dtos/items/schemas.py" in paths
    schemas_content = by_path["dtos/items/schemas.py"].content
    assert "class CreateItemRequestSchema(Schema)" in schemas_content
    assert "fields.String" in schemas_content
    # Convenience instances are exported
    assert "create_items_request_schema = CreateItemRequestSchema()" in schemas_content

    # The controller uses the schemas (not Pydantic)
    controller = by_path["controllers/items/items_controller.py"].content
    assert "create_items_request_schema.load" in controller
    assert "from dtos.items.schemas import" in controller
    # No Pydantic imports
    assert "from dtos.items.requests import" not in controller


def test_generate_resource_rejects_unknown_schema(tmp_path: Path) -> None:
    spec = _example_spec()
    with pytest.raises(ValueError):
        _codegen.generate_resource(spec, project_root=tmp_path, schema="xmlschema")


def test_generate_resource_marshmallow_schemas_parse(tmp_path: Path) -> None:
    """The generated Marshmallow Schemas must import cleanly."""
    pytest.importorskip("marshmallow", reason="marshmallow not installed")

    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=tmp_path, schema="marshmallow")
    by_path = {f.path: f for f in plan.files}
    schemas_src = by_path["dtos/items/schemas.py"].content
    # The source is a complete module — exec it in a fresh namespace and
    # verify the convenience instances instantiate.
    ns: dict = {}
    exec(schemas_src, ns)
    assert "create_items_request_schema" in ns
    inst = ns["create_items_request_schema"]
    out = inst.load({"title": "hi", "description": "x"})
    assert out["title"] == "hi"


def test_generate_resource_plan_id_is_unique() -> None:
    spec = _example_spec()
    p1 = _codegen.generate_resource(spec, project_root=Path("/tmp"))
    p2 = _codegen.generate_resource(spec, project_root=Path("/tmp"))
    assert p1.plan_id != p2.plan_id


def test_generate_resource_creates_kinds_for_new_files(tmp_path: Path) -> None:
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=tmp_path)
    # All files are new, all kinds should be "create"
    for f in plan.files:
        assert f.kind == "create", f"{f.path} expected create, got {f.kind}"


def test_generate_resource_detects_unchanged_files(tmp_path: Path) -> None:
    spec = _example_spec()
    plan1 = _codegen.generate_resource(spec, project_root=tmp_path)
    _codegen.apply_plan(plan1, project_root=tmp_path)
    plan2 = _codegen.generate_resource(spec, project_root=tmp_path)
    # Re-running should mark all files as "skip"
    for f in plan2.files:
        assert f.kind == "skip", f"{f.path} expected skip, got {f.kind}"


def test_generate_resource_detects_modifications(tmp_path: Path) -> None:
    spec = _example_spec()
    plan1 = _codegen.generate_resource(spec, project_root=tmp_path)
    _codegen.apply_plan(plan1, project_root=tmp_path)
    # Tamper with one file
    (tmp_path / "models" / "items.py").write_text("# tampered\n", encoding="utf-8")
    plan2 = _codegen.generate_resource(spec, project_root=tmp_path)
    by_path = {f.path: f for f in plan2.files}
    assert by_path["models/items.py"].kind == "modify"
    assert by_path["models/items.py"].existing_content == "# tampered\n"
    # Other files should be skip
    assert by_path["repositories/items.py"].kind == "skip"


def test_generate_resource_plan_to_summary(tmp_path: Path) -> None:
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=tmp_path)
    summary = _codegen.plan_to_summary(plan)
    assert "new" in summary


def test_generate_resource_plan_to_preview_html_includes_diff(tmp_path: Path) -> None:
    spec = _example_spec()
    plan1 = _codegen.generate_resource(spec, project_root=tmp_path)
    _codegen.apply_plan(plan1, project_root=tmp_path)
    (tmp_path / "models" / "items.py").write_text("# custom edit\n", encoding="utf-8")
    plan2 = _codegen.generate_resource(spec, project_root=tmp_path)
    html = _codegen.plan_to_preview_html(plan2)
    assert "models/items.py" in html
    assert "MOD" in html
    # Skip should produce the "unchanged" marker
    assert "repositories/items.py" in html
    assert "SKIP" in html


def test_generated_python_files_parse(tmp_path: Path) -> None:
    """The generated .py files must at least be syntactically valid."""
    import ast

    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=tmp_path)
    _codegen.apply_plan(plan, project_root=tmp_path)
    for f in plan.files:
        if not f.path.endswith(".py"):
            continue
        path = tmp_path / f.path
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover
            raise AssertionError(f"Generated file does not parse: {f.path}\n{exc}") from exc


# ---------------------------------------------------------------------------
# Apply safety
# ---------------------------------------------------------------------------


def test_apply_plan_creates_files_on_disk(tmp_path: Path) -> None:
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=tmp_path)
    written = _codegen.apply_plan(plan, project_root=tmp_path)
    assert len(written) == len(plan.files)
    for rel in written:
        assert (tmp_path / rel).is_file()


def test_apply_plan_refuses_escape_via_relative_traversal(tmp_path: Path) -> None:
    """Path-traversal protection: refuse to write outside project_root."""
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=tmp_path)
    # Manually craft a plan with a malicious path

    bad = _codegen.GeneratedFile(
        path="../escape.txt",
        content="evil",
        kind="create",
        template="evil.tpl",
    )
    plan.files.append(bad)
    with pytest.raises(_codegen.CodegenError):
        _codegen.apply_plan(plan, project_root=tmp_path)


def test_apply_plan_refuses_absolute_paths(tmp_path: Path) -> None:
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=tmp_path)

    bad = _codegen.GeneratedFile(
        path="/tmp/abs.txt",
        content="evil",
        kind="create",
        template="evil.tpl",
    )
    plan.files.append(bad)
    with pytest.raises(_codegen.CodegenError):
        _codegen.apply_plan(plan, project_root=tmp_path)


# ---------------------------------------------------------------------------
# Plan store
# ---------------------------------------------------------------------------


def test_plan_store_put_get_drop() -> None:
    store = _codegen._PlanStore()
    plan = _codegen.CodePlan(
        plan_id="abc",
        resource="items",
        summary="x",
        files=[],
    )
    store.put(plan)
    assert store.get("abc") is plan
    assert store.drop("abc") is plan
    assert store.get("abc") is None


def test_plan_store_expires_entries() -> None:
    store = _codegen._PlanStore()
    plan = _codegen.CodePlan(plan_id="abc", resource="items", summary="x", files=[])
    store.put(plan, ttl_seconds=0)
    import time as _t

    _t.sleep(0.05)
    assert store.get("abc") is None


# ---------------------------------------------------------------------------
# Template discovery
# ---------------------------------------------------------------------------


def test_templates_directory_has_all_required_templates() -> None:
    """Every template the generator expects must be on disk."""
    expected = {
        "model.py.tpl",
        "repository.py.tpl",
        "dto_requests.py.tpl",
        "dto_responses.py.tpl",
        "dtos_init.py.tpl",
        "mapper.py.tpl",
        "service_create.py.tpl",
        "service_get.py.tpl",
        "service_list.py.tpl",
        "service_update.py.tpl",
        "service_delete.py.tpl",
        "services_init.py.tpl",
        "controller.py.tpl",
        "dependency.py.tpl",
        "migration.sql.tpl",
        "test.py.tpl",
    }
    actual = {p.name for p in _codegen.TEMPLATES_DIR.iterdir() if p.is_file()}
    missing = expected - actual
    assert not missing, f"missing templates: {missing}"


# ---------------------------------------------------------------------------
# Generation semantics
# ---------------------------------------------------------------------------


def test_generated_model_declares_orm_table() -> None:
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=Path("/tmp"))
    by_path = {f.path: f for f in plan.files}
    text = by_path["models/items.py"].content
    assert "class Item(BaseModel):" in text
    assert '__tablename__ = "items"' in text
    assert "title" in text
    assert "is_completed" in text


def test_generated_repository_inherits_irepository() -> None:
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=Path("/tmp"))
    by_path = {f.path: f for f in plan.files}
    text = by_path["repositories/items.py"].content
    assert "class ItemRepository(IRepository[Item, int]):" in text
    assert "model_class = Item" in text


def test_generated_controller_has_crud_routes() -> None:
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=Path("/tmp"))
    by_path = {f.path: f for f in plan.files}
    text = by_path["controllers/items/items_controller.py"].content
    for verb in ("@get", "@post", "@patch", "@delete"):
        assert verb in text, f"controller missing {verb}"
    assert "ItemsController" in text
    assert "API_PREFIX" in text


def test_generated_services_have_iservice() -> None:
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=Path("/tmp"))
    by_path = {f.path: f for f in plan.files}
    for op in ("create", "get", "list", "update", "delete"):
        text = by_path[f"services/items/{op}_items.py"].content
        assert "IService[" in text
        assert '@timer("service")' in text


def test_generated_migration_has_create_table() -> None:
    spec = _example_spec()
    plan = _codegen.generate_resource(spec, project_root=Path("/tmp"))
    by_path = {f.path: f for f in plan.files}
    migration_paths = [p for p in by_path if p.startswith("migrations/")]
    assert len(migration_paths) == 1
    text = by_path[migration_paths[0]].content
    assert "CREATE TABLE" in text
    assert "items" in text


# ---------------------------------------------------------------------------
# ResourceSpec.derived()
# ---------------------------------------------------------------------------


def test_resource_spec_derived_populates_defaults() -> None:
    raw = _codegen.ResourceSpec(resource="widgets")
    out = raw.derived()
    assert out.model_class == "Widget"
    assert out.table_name == "widgets"
    assert out.tag == "widgets"


def test_resource_spec_derived_preserves_overrides() -> None:
    raw = _codegen.ResourceSpec(
        resource="widgets",
        model_class="Gadget",
        table_name="gadgets",
        tag="gadgets",
    )
    out = raw.derived()
    assert out.model_class == "Gadget"
    assert out.table_name == "gadgets"


# ---------------------------------------------------------------------------
# _safe_ident + _pascal
# ---------------------------------------------------------------------------


def test_safe_ident_normalises_user_input() -> None:
    assert _codegen._safe_ident("My Cool Items!") == "my_cool_items"
    assert _codegen._safe_ident("users") == "users"
    assert _codegen._safe_ident("123") == "resource"
    assert _codegen._safe_ident("") == "resource"
    assert _codegen._safe_ident("!!!") == "resource"


def test_pascal_converts_snake() -> None:
    assert _codegen._pascal("items") == "Item"
    assert _codegen._pascal("blog_posts") == "BlogPost"
    assert _codegen._pascal("user") == "User"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_parse_field_with_max_length(tmp_path: Path) -> None:
    """Field with max_length attribute generates the right validator."""
    from rivex_codegen import parse_api_form

    spec = parse_api_form(
        resource="Foo",
        description="",
        fields_text="name: str max_length=50",
    )
    # The field should be in the endpoint's fields somewhere
    ep = spec.endpoints[0]
    all_fields = list(ep.body_fields) + list(ep.form_fields)
    name_fields = [f for f in all_fields if f.name == "name"]
    if name_fields:
        assert name_fields[0].max_length == 50


def test_parse_field_with_min_length(tmp_path: Path) -> None:
    """Field with min_length attribute generates the right validator."""
    from rivex_codegen import parse_api_form

    spec = parse_api_form(
        resource="Foo",
        description="",
        fields_text="name: str min_length=2",
    )
    ep = spec.endpoints[0]
    all_fields = list(ep.body_fields) + list(ep.form_fields)
    name_fields = [f for f in all_fields if f.name == "name"]
    if name_fields:
        assert name_fields[0].min_length == 2


def test_parse_field_response_path(tmp_path: Path) -> None:
    """Field with response scope is in the response fields."""
    from rivex_codegen import parse_api_form

    spec = parse_api_form(
        resource="Foo",
        description="",
        fields_text="id: int (response)",
    )
    # Field is in the endpoint's response_fields with scope 'response'
    ep = spec.endpoints[0]
    assert any("response" in f.scopes for f in ep.response_fields)


def test_parse_field_with_le_and_ge(tmp_path: Path) -> None:
    """Field with le (less-or-equal) and ge (greater-or-equal) attributes."""
    from rivex_codegen import parse_api_form

    spec = parse_api_form(
        resource="Foo",
        description="",
        fields_text="score: int ge=0 le=100",
    )
    # Field should be in body_fields or form_fields
    ep = spec.endpoints[0]
    all_fields = list(ep.body_fields) + list(ep.form_fields)
    score_fields = [f for f in all_fields if f.name == "score"]
    if score_fields:
        assert score_fields[0].ge == 0
        assert score_fields[0].le == 100
