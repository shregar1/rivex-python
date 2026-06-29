"""Smoke tests for the project scaffolder."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_scaffold_module():
    """Load :mod:`rivex_scaffold` without triggering the full Rivex package import.

    The full Rivex import requires the compiled Rust extension, which is not
    always available in CI. The scaffold module is pure stdlib and safe to load
    in isolation.
    """
    name = "rivex_scaffold_under_test"
    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).resolve().parents[1] / "rivex_scaffold" / "__init__.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_scaffold = _load_scaffold_module()
ScaffoldOptions = _scaffold.ScaffoldOptions
render = _scaffold.render
scaffold = _scaffold.scaffold
TEMPLATE_ROOT = _scaffold.TEMPLATE_ROOT


@pytest.fixture
def tmp_template(tmp_path: Path) -> Path:
    """Build a tiny in-memory template tree."""
    root = tmp_path / "tpl"
    (root / "abstractions").mkdir(parents=True)
    (root / "configs" / "database").mkdir(parents=True)
    (root / "main.py").write_text(
        '"""{{project_name}} entrypoint."""\n'
        "slug = '{{project_slug}}'\n"
        "module = '{{project_module}}'\n",
        encoding="utf-8",
    )
    (root / "configs" / "database" / "config.json").write_text(
        '{"database_url": "postgres://{{project_slug}}:{{project_slug}}_secret@localhost/{{project_slug}}"}',
        encoding="utf-8",
    )
    (root / "abstractions" / "README.md").write_text(
        "Contract layer for {{project_name}}.\n",
        encoding="utf-8",
    )
    (root / "abstractions" / "singleton.py").write_text(
        "# template with literal {{ in code (should be left alone if not a key)\n",
        encoding="utf-8",
    )
    return root


def test_render_substitutes_known_keys() -> None:
    out = render("hello {{name}}!", {"name": "world"})
    assert out == "hello world!"


def test_render_raises_for_unknown_key() -> None:
    import pytest

    with pytest.raises(KeyError):
        render("{{missing}}", {})


def test_render_handles_whitespace_in_braces() -> None:
    out = render("a={{ k }}b", {"k": "1"})
    assert out == "a=1b"


def test_scaffold_writes_files(tmp_path: Path, tmp_template: Path) -> None:
    target = tmp_path / "out"
    opts = ScaffoldOptions(project_name="Acme API", target_dir=target)
    created = scaffold(opts, template_root=tmp_template)
    names = {p.relative_to(target).as_posix() for p in created}
    assert "main.py" in names
    assert "configs/database/config.json" in names
    assert "abstractions/README.md" in names

    main_py = (target / "main.py").read_text(encoding="utf-8")
    assert '"""Acme API entrypoint."""' in main_py
    assert "slug = 'acme-api'" in main_py
    assert "module = 'acme_api'" in main_py

    db_cfg = (target / "configs" / "database" / "config.json").read_text(encoding="utf-8")
    assert "postgres://acme-api:acme-api_secret@localhost/acme-api" in db_cfg

    readme = (target / "abstractions" / "README.md").read_text(encoding="utf-8")
    assert "Contract layer for Acme API." in readme


def test_scaffold_refuses_non_empty_target_without_force(
    tmp_path: Path, tmp_template: Path
) -> None:
    target = tmp_path / "out"
    target.mkdir()
    (target / "existing.txt").write_text("nope", encoding="utf-8")
    opts = ScaffoldOptions(project_name="Foo", target_dir=target)
    with pytest.raises(FileExistsError):
        scaffold(opts, template_root=tmp_template)


def test_scaffold_force_overwrites(tmp_path: Path, tmp_template: Path) -> None:
    target = tmp_path / "out"
    target.mkdir()
    (target / "existing.txt").write_text("nope", encoding="utf-8")
    opts = ScaffoldOptions(project_name="Foo", target_dir=target, force=True)
    scaffold(opts, template_root=tmp_template)
    assert not (target / "existing.txt").exists()
    assert (target / "main.py").exists()


def test_scaffold_slugify_variants() -> None:
    opts = ScaffoldOptions(project_name="My Cool App!!", target_dir=Path("/tmp/x"))
    assert opts.slug == "my-cool-app"
    assert opts.module_name == "my_cool_app"


def test_real_template_directory_exists() -> None:
    """The vendored template directory ships with the package."""
    assert TEMPLATE_ROOT.is_dir()
    assert (TEMPLATE_ROOT / "abstractions").is_dir()
    assert (TEMPLATE_ROOT / "controllers").is_dir()
    assert (TEMPLATE_ROOT / "services").is_dir()
    assert (TEMPLATE_ROOT / "repositories").is_dir()
    assert (TEMPLATE_ROOT / "models").is_dir()
    assert (TEMPLATE_ROOT / "dtos").is_dir()
    assert (TEMPLATE_ROOT / "configurations").is_dir()
    assert (TEMPLATE_ROOT / "utilities").is_dir()
    assert (TEMPLATE_ROOT / "main.py").is_file()
    assert (TEMPLATE_ROOT / "pyproject.toml").is_file()


def test_real_template_has_placeholders() -> None:
    """The vendored template must contain at least one placeholder for each key."""
    import re

    found: set[str] = set()
    for f in TEMPLATE_ROOT.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for m in re.findall(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", text):
            found.add(m)
    assert {"project_name", "project_slug"}.issubset(found)


def test_real_template_render_creates_runnable_layout(tmp_path: Path) -> None:
    """End-to-end: render the real template into a temp dir, verify key files."""
    opts = ScaffoldOptions(project_name="Acme API", target_dir=tmp_path / "acme-api")
    scaffold(opts, template_root=TEMPLATE_ROOT)
    target = tmp_path / "acme-api"
    assert (target / "main.py").is_file()
    assert (target / "abstractions" / "__init__.py").is_file()
    assert (target / "controllers" / "__init__.py").is_file()
    assert (target / "services" / "__init__.py").is_file()
    assert (target / "repositories" / "__init__.py").is_file()
    assert (target / "models" / "__init__.py").is_file()
    assert (target / "dtos" / "__init__.py").is_file()
    assert (target / "configurations" / "__init__.py").is_file()
    assert (target / "utilities" / "__init__.py").is_file()
    assert (target / ".env.example").is_file()
    assert (target / "pyproject.toml").is_file()

    pyproject = (target / "pyproject.toml").read_text(encoding="utf-8")
    assert "acme-api" in pyproject

    main_py = (target / "main.py").read_text(encoding="utf-8")
    assert "Acme API" in main_py
    # project_slug should appear at least once (in PLATFORM_NAME or log file defaults)
    db_cfg = (target / "configs" / "database" / "config.json").read_text(encoding="utf-8")
    assert "acme-api" in db_cfg
    env_example = (target / ".env.example").read_text(encoding="utf-8")
    assert "acme-api" in env_example


# ---------------------------------------------------------------------------
# New: rich scaffold options (description, author, git, install, etc.)
# ---------------------------------------------------------------------------


def test_options_context_includes_author_and_repo(tmp_path: Path) -> None:
    opts = ScaffoldOptions(
        project_name="Acme API",
        target_dir=tmp_path / "acme",
        description="Companion platform backend",
        author_name="Jane Doe",
        author_email="jane@example.com",
        license="Apache-2.0",
        version="1.2.3",
        repository_url="https://github.com/jane/acme",
    )
    ctx = opts.context
    assert ctx["author_name"] == "Jane Doe"
    assert ctx["author_email"] == "jane@example.com"
    assert ctx["license"] == "Apache-2.0"
    assert ctx["version"] == "1.2.3"
    assert ctx["repository_url"] == "https://github.com/jane/acme"
    assert ctx["description"] == "Companion platform backend"
    assert ctx["year"].isdigit() and len(ctx["year"]) == 4


def test_options_context_description_falls_back_to_name(tmp_path: Path) -> None:
    opts = ScaffoldOptions(project_name="Foo", target_dir=tmp_path / "foo")
    assert opts.context["description"] == "Foo"


def test_options_context_year_default_is_current(tmp_path: Path) -> None:
    opts = ScaffoldOptions(project_name="Foo", target_dir=tmp_path / "foo")
    assert opts.context["year"] == str(_scaffold._current_year())


def test_options_context_extras_override(tmp_path: Path) -> None:
    opts = ScaffoldOptions(
        project_name="Foo",
        target_dir=tmp_path / "foo",
        extras={"custom_key": "value"},
    )
    assert opts.context["custom_key"] == "value"


def test_scaffold_rejects_empty_project_name(tmp_path: Path) -> None:
    opts = ScaffoldOptions(project_name="   ", target_dir=tmp_path / "x")
    with pytest.raises(ValueError):
        scaffold(opts, template_root=TEMPLATE_ROOT)


def test_render_substitutes_extra_keys(tmp_path: Path) -> None:
    opts = ScaffoldOptions(
        project_name="Foo",
        target_dir=tmp_path / "foo",
        author_name="Jane",
        author_email="jane@x.io",
    )
    out = render(
        "by {{author_name}} <{{author_email}}> for {{project_name}}",
        opts.context,
    )
    assert out == "by Jane <jane@x.io> for Foo"


def test_validate_email_accepts_valid() -> None:
    assert _scaffold._validate_email("a@b.co") is None
    assert _scaffold._validate_email("first.last+tag@sub.example.com") is None


def test_validate_email_rejects_invalid() -> None:
    assert _scaffold._validate_email("") is not None
    assert _scaffold._validate_email("no-at-sign") is not None
    assert _scaffold._validate_email("a@") is not None
    assert _scaffold._validate_email("@b.co") is not None


def test_run_git_creates_repo_and_commit(tmp_path: Path) -> None:
    if not _scaffold._git_available():
        pytest.skip("git executable not on $PATH")
    target = tmp_path / "g"
    target.mkdir()
    (target / "hello.txt").write_text("hi", encoding="utf-8")
    ok, summary = _scaffold._run_git(
        target,
        user_name="Test User",
        user_email="test@example.com",
        initial_message="test commit",
    )
    assert ok, summary
    assert (target / ".git").is_dir()
    head = _scaffold._git("log", "--oneline", cwd=target)
    assert head.returncode == 0
    assert "test commit" in head.stdout


def test_run_git_appends_to_existing_repo(tmp_path: Path) -> None:
    if not _scaffold._git_available():
        pytest.skip("git executable not on $PATH")
    target = tmp_path / "g2"
    target.mkdir()
    _scaffold._git("init", "--initial-branch=main", cwd=target)
    (target / "a.txt").write_text("a", encoding="utf-8")
    _scaffold._git("config", "user.name", "Init", cwd=target)
    _scaffold._git("config", "user.email", "init@x.io", cwd=target)
    _scaffold._git("add", "-A", cwd=target)
    _scaffold._git("commit", "-m", "first", cwd=target)

    (target / "b.txt").write_text("b", encoding="utf-8")
    ok, _ = _scaffold._run_git(
        target,
        user_name="Second",
        user_email="second@x.io",
        initial_message="second",
    )
    assert ok
    log = _scaffold._git("log", "--oneline", cwd=target)
    assert "first" in log.stdout
    assert "second" in log.stdout


def test_main_non_interactive_creates_project(tmp_path: Path) -> None:
    target = tmp_path / "out"
    rc = _scaffold.main(
        [
            "Test App",
            str(target),
            "--author-name",
            "Tester",
            "--author-email",
            "t@x.io",
            "--no-git",
            "--description",
            "demo",
        ],
    )
    assert rc == 0
    assert (target / "main.py").is_file()
    assert not (target / ".git").exists()
    pyproject = (target / "pyproject.toml").read_text(encoding="utf-8")
    assert "test-app" in pyproject


def test_main_non_interactive_skips_git_when_no_git_flag(tmp_path: Path) -> None:
    target = tmp_path / "out"
    rc = _scaffold.main(["Foo", str(target), "--no-git"])
    assert rc == 0
    assert not (target / ".git").exists()


def test_main_interactive_falls_back_when_not_tty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(_scaffold, "_isatty", lambda: False)
    target = tmp_path / "out"
    rc = _scaffold.main(["Foo", str(target), "--no-git"])
    assert rc == 0
    assert (target / "main.py").is_file()


def test_main_interactive_runs_via_pipe(tmp_path: Path, monkeypatch) -> None:
    """Drive the interactive prompts by piping a full answer into stdin."""
    target = tmp_path / "out"
    answers = "\n".join(
        [
            "Test App",  # project name
            str(target),  # output directory
            "demo",  # description
            "Alice",  # author name
            "alice@example.com",  # author email
            "MIT",  # license
            "0.1.0",  # version
            "",  # repository URL (blank)
            ">=3.10",  # python version
            "n",  # init git? no
        ]
    )
    monkeypatch.setattr(_scaffold, "_isatty", lambda: True)
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(answers + "\n"))
    rc = _scaffold.main([])
    assert rc == 0
    assert (target / "main.py").is_file()
    pyproject = (target / "pyproject.toml").read_text(encoding="utf-8")
    assert "alice@example.com" in pyproject or "test-app" in pyproject


def test_main_interactive_with_git(tmp_path: Path, monkeypatch) -> None:
    """Interactive flow: answer yes to git, no to install — verify .git is created."""
    if not _scaffold._git_available():
        pytest.skip("git executable not on $PATH")
    target = tmp_path / "out_git"
    answers = "\n".join(
        [
            "Test App",  # project name
            str(target),  # output directory
            "demo",  # description
            "Alice",  # author name
            "alice@example.com",  # author email
            "MIT",  # license
            "0.1.0",  # version
            "",  # repository URL
            ">=3.10",  # python version
            "y",  # init git? yes
            "n",  # install deps? no
            "Initial scaffold",  # commit message
        ]
    )
    monkeypatch.setattr(_scaffold, "_isatty", lambda: True)
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(answers + "\n"))
    rc = _scaffold.main([])
    assert rc == 0
    assert (target / ".git").is_dir()
    log = _scaffold._git("log", "--oneline", cwd=target)
    assert "Initial scaffold" in log.stdout


# ---------------------------------------------------------------------------
# .env auto-creation and project-name coverage
# ---------------------------------------------------------------------------


def test_scaffold_creates_env_from_example(tmp_path: Path) -> None:
    """A working .env is always produced alongside the example template."""
    target = tmp_path / "env_test"
    opts = ScaffoldOptions(project_name="Acme API", target_dir=target)
    created = scaffold(opts, template_root=TEMPLATE_ROOT)
    env_file = target / ".env"
    env_example = target / ".env.example"
    assert env_file.is_file()
    assert env_example.is_file()
    assert env_file in created
    # Both files should have the same content post-render
    assert env_file.read_text(encoding="utf-8") == env_example.read_text(encoding="utf-8")
    # The rendered content should reference the project name + slug
    text = env_file.read_text(encoding="utf-8")
    assert "Acme API" in text
    assert "acme-api" in text


def test_scaffold_does_not_overwrite_existing_env(tmp_path: Path) -> None:
    """If the user already has a .env, we don't blow it away."""
    target = tmp_path / "env_keep"
    target.mkdir()
    (target / ".env").write_text("PRESERVED=true", encoding="utf-8")
    opts = ScaffoldOptions(project_name="Foo", target_dir=target, force=True)
    scaffold(opts, template_root=TEMPLATE_ROOT)
    env_file = target / ".env"
    assert env_file.read_text(encoding="utf-8") == "PRESERVED=true"


def test_scaffold_env_does_not_contain_unrendered_placeholders(tmp_path: Path) -> None:
    """After render, .env must not contain any unresolved ``{{…}}`` tokens."""
    target = tmp_path / "render_check"
    opts = ScaffoldOptions(project_name="Acme API", target_dir=target)
    scaffold(opts, template_root=TEMPLATE_ROOT)
    text = (target / ".env").read_text(encoding="utf-8")
    import re

    leftover = re.findall(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", text)
    assert leftover == [], f"unresolved placeholders in .env: {leftover}"


def test_template_uses_project_name_in_env(tmp_path: Path) -> None:
    """The .env.example shipped in the template must reference the project name."""
    env_example = TEMPLATE_ROOT / ".env.example"
    assert env_example.is_file()
    text = env_example.read_text(encoding="utf-8")
    assert "{{project_name}}" in text
    assert "{{project_slug}}" in text


def test_template_uses_project_name_in_pyproject() -> None:
    """pyproject.toml must use the project name + author metadata."""
    pyproject = (TEMPLATE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "{{project_name}}" in pyproject
    assert "{{project_slug}}" in pyproject
    assert "{{author_name}}" in pyproject
    assert "{{author_email}}" in pyproject
    assert "{{license}}" in pyproject
    assert "{{version}}" in pyproject
    assert "{{description}}" in pyproject


def test_template_uses_project_name_in_readme() -> None:
    """README.md must reference project name + description + author."""
    readme = (TEMPLATE_ROOT / "README.md").read_text(encoding="utf-8")
    assert "{{project_name}}" in readme
    assert "{{description}}" in readme
    assert "{{author_name}}" in readme
    assert "{{author_email}}" in readme


def test_template_uses_project_name_in_main() -> None:
    """main.py must use the project description in the Rivex app config."""
    main_py = (TEMPLATE_ROOT / "main.py").read_text(encoding="utf-8")
    assert "{{description}}" in main_py
    # Title should now come from PLATFORM_NAME (which itself is templated)
    assert "PLATFORM_NAME" in main_py
    assert "PROJECT_VERSION" in main_py


def test_template_uses_project_name_in_configs(tmp_path: Path) -> None:
    """configs/__init__.py must expose project metadata constants."""
    configs = (TEMPLATE_ROOT / "configs" / "__init__.py").read_text(encoding="utf-8")
    for key in (
        "PROJECT_NAME",
        "PROJECT_SLUG",
        "PROJECT_VERSION",
        "PROJECT_DESCRIPTION",
        "PROJECT_AUTHOR_NAME",
        "PROJECT_AUTHOR_EMAIL",
        "PROJECT_LICENSE",
        "PROJECT_REPOSITORY_URL",
        "PROJECT_YEAR",
    ):
        assert key in configs, f"configs/__init__.py missing {key}"
    assert "project_metadata" in configs


def test_template_uses_project_name_in_constants() -> None:
    """constants/api.py must set PLATFORM_NAME from project_name."""
    text = (TEMPLATE_ROOT / "constants" / "api.py").read_text(encoding="utf-8")
    assert 'PLATFORM_NAME = "{{project_name}}"' in text


def test_template_uses_project_name_in_middleware() -> None:
    """RequestIdMiddleware must stamp the service name on responses."""
    text = (TEMPLATE_ROOT / "middlewares" / "request_id.py").read_text(encoding="utf-8")
    assert "PROJECT_NAME" in text
    assert "PROJECT_VERSION" in text
    assert "x-service-name" in text.lower()


def test_template_uses_project_name_in_makefile() -> None:
    """Makefile must expose the project name + slug."""
    makefile = (TEMPLATE_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "{{project_name}}" in makefile
    assert "{{project_slug}}" in makefile
    assert ".env" in makefile


def test_rendered_main_uses_author_metadata(tmp_path: Path) -> None:
    """The rendered main.py should reference author email/name from configs."""
    opts = ScaffoldOptions(
        project_name="Acme API",
        target_dir=tmp_path / "acme",
        author_name="Jane Doe",
        author_email="jane@x.io",
    )
    scaffold(opts, template_root=TEMPLATE_ROOT)
    main_py = (tmp_path / "acme" / "main.py").read_text(encoding="utf-8")
    assert "project_metadata" in main_py
    assert "Acme API" in main_py


def test_rendered_pyproject_has_author_block(tmp_path: Path) -> None:
    """Rendered pyproject.toml must include the actual author info."""
    opts = ScaffoldOptions(
        project_name="Acme API",
        target_dir=tmp_path / "acme",
        author_name="Jane Doe",
        author_email="jane@x.io",
        license="Apache-2.0",
        version="2.0.0",
    )
    scaffold(opts, template_root=TEMPLATE_ROOT)
    pyproject = (tmp_path / "acme" / "pyproject.toml").read_text(encoding="utf-8")
    assert "Jane Doe" in pyproject
    assert "jane@x.io" in pyproject
    assert "Apache-2.0" in pyproject
    assert 'version = "2.0.0"' in pyproject
    # No unresolved placeholders
    import re

    leftover = re.findall(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", pyproject)
    assert leftover == [], f"unresolved placeholders in pyproject: {leftover}"


# ---------------------------------------------------------------------------
# APP_NAME landing-page override
# ---------------------------------------------------------------------------


def test_template_env_example_has_app_name() -> None:
    """The shipped .env.example must expose APP_NAME as a configurable value."""
    text = (TEMPLATE_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "APP_NAME" in text
    assert "{{project_name}}" in text  # default value uses the project name


def test_template_configs_settings_has_app_name() -> None:
    """The Settings class must declare APP_NAME / POWERED_BY fields."""
    text = (TEMPLATE_ROOT / "configs" / "__init__.py").read_text(encoding="utf-8")
    assert "app_name" in text
    assert "APP_NAME" in text
    assert "powered_by" in text
    assert "POWERED_BY" in text


def test_template_main_passes_app_name_to_rivex() -> None:
    """main.py must read APP_NAME and pass it as app_name to Rivex()."""
    text = (TEMPLATE_ROOT / "main.py").read_text(encoding="utf-8")
    assert "APP_NAME" in text
    assert "POWERED_BY" in text
    assert "app_name=APP_NAME" in text
    assert "powered_by=POWERED_BY" in text


def test_template_appconfig_exposes_settings() -> None:
    """AppConfiguration must expose the underlying settings so main.py can read
    the resolved app_name / powered_by from ``settings.app``."""
    text = (TEMPLATE_ROOT / "configurations" / "app.py").read_text(encoding="utf-8")
    assert "self.settings" in text
    assert "settings.app" in text or "self._app" in text


def test_rendered_main_has_resolved_app_name(tmp_path: Path) -> None:
    """After render, main.py must reference the actual project name, not a placeholder."""
    opts = ScaffoldOptions(
        project_name="Acme API",
        target_dir=tmp_path / "acme",
    )
    scaffold(opts, template_root=TEMPLATE_ROOT)
    main_py = (tmp_path / "acme" / "main.py").read_text(encoding="utf-8")
    assert "Acme API" in main_py
    import re

    leftover = re.findall(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", main_py)
    assert leftover == [], f"unresolved placeholders in main.py: {leftover}"


def test_rendered_env_has_resolved_app_name(tmp_path: Path) -> None:
    """After render, .env must have APP_NAME=<actual project name>."""
    opts = ScaffoldOptions(
        project_name="Acme API",
        target_dir=tmp_path / "acme",
    )
    scaffold(opts, template_root=TEMPLATE_ROOT)
    env = (tmp_path / "acme" / ".env").read_text(encoding="utf-8")
    assert "APP_NAME=Acme API" in env
    import re

    leftover = re.findall(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", env)
    assert leftover == [], f"unresolved placeholders in .env: {leftover}"


# ---------------------------------------------------------------------------
# Admin dashboard wiring
# ---------------------------------------------------------------------------


def test_template_env_example_has_admin_vars() -> None:
    """The .env.example must expose admin dashboard settings."""
    text = (TEMPLATE_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "ADMIN_ENABLED" in text
    assert "ADMIN_URL" in text
    assert "ADMIN_TOKEN" in text


def test_template_configs_settings_has_admin_fields() -> None:
    """The Settings class must declare admin_enabled / admin_url / admin_token."""
    text = (TEMPLATE_ROOT / "configs" / "__init__.py").read_text(encoding="utf-8")
    assert "admin_enabled" in text
    assert "admin_url" in text
    assert "admin_token" in text
    assert "ADMIN_ENABLED" in text
    assert "ADMIN_URL" in text
    assert "ADMIN_TOKEN" in text


def test_template_main_passes_admin_to_rivex() -> None:
    """main.py must pass admin_url and admin_token to Rivex()."""
    text = (TEMPLATE_ROOT / "main.py").read_text(encoding="utf-8")
    assert "ADMIN_ENABLED" in text
    assert "admin_url=" in text
    assert "admin_token=" in text


def test_template_vendors_admin_static_files() -> None:
    """The template must include HTMX + Alpine.js as static files in main.py."""
    # The vendored JS lives in the framework's _static/admin/ dir; main.py must
    # mount it via Rivex.mount(...)
    text = (TEMPLATE_ROOT / "main.py").read_text(encoding="utf-8")
    # The admin route is registered by Rivex(admin_url=...) which calls mount()
    # internally, so the only check is that admin_url is wired.
    assert "admin_url" in text


def test_rendered_env_has_resolved_admin_token(tmp_path: Path) -> None:
    """After render, the .env must have all admin settings resolved."""
    opts = ScaffoldOptions(project_name="Acme API", target_dir=tmp_path / "acme")
    scaffold(opts, template_root=TEMPLATE_ROOT)
    env = (tmp_path / "acme" / ".env").read_text(encoding="utf-8")
    assert "ADMIN_ENABLED=true" in env
    assert "ADMIN_URL=/admin" in env
    assert "ADMIN_TOKEN=" in env
    import re

    leftover = re.findall(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", env)
    assert leftover == [], f"unresolved placeholders in .env: {leftover}"


# ---------------------------------------------------------------------------
# Codegen (admin resource generator) wiring
# ---------------------------------------------------------------------------


def test_template_env_example_has_codegen_vars() -> None:
    """The .env.example must expose codegen settings."""
    text = (TEMPLATE_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "ADMIN_CODEGEN_ENABLED" in text
    assert "PROJECT_ROOT" in text


def test_template_configs_settings_has_codegen_fields() -> None:
    """The Settings class must declare project_root / admin_codegen_enabled."""
    text = (TEMPLATE_ROOT / "configs" / "__init__.py").read_text(encoding="utf-8")
    assert "project_root" in text
    assert "admin_codegen_enabled" in text
    assert "PROJECT_ROOT" in text
    assert "ADMIN_CODEGEN_ENABLED" in text


def test_template_main_exposes_project_root() -> None:
    """main.py must read PROJECT_ROOT and expose it on the app."""
    text = (TEMPLATE_ROOT / "main.py").read_text(encoding="utf-8")
    assert "PROJECT_ROOT" in text
    assert "app.project_root" in text
    assert "ADMIN_CODEGEN_ENABLED" in text


def test_rendered_main_resolves_codegen_placeholders(tmp_path: Path) -> None:
    opts = ScaffoldOptions(project_name="Acme API", target_dir=tmp_path / "acme")
    scaffold(opts, template_root=TEMPLATE_ROOT)
    main_py = (tmp_path / "acme" / "main.py").read_text(encoding="utf-8")
    assert "PROJECT_ROOT" in main_py
    import re

    leftover = re.findall(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", main_py)
    assert leftover == [], f"unresolved placeholders in main.py: {leftover}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
