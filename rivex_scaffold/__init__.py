"""Project scaffolder — generates a layered Rivex backend from the bundled template.

Public entry points:
    - :class:`ScaffoldOptions` — parsed CLI options.
    - :func:`scaffold` — perform the copy + templating.
    - :func:`render` — render a single template string with placeholders.

The template is bundled in ``rivex._scaffold_template`` (a copy of the canonical
``mvc/`` directory at the root of this repository). Every ``{{placeholder}}`` token
in any file is rendered through :func:`render` using the values from
:class:`ScaffoldOptions`.

Placeholder reference:

    - ``{{project_name}}``   — human-readable name (e.g. ``Acme API``)
    - ``{{project_slug}}``   — filesystem / db-safe slug (e.g. ``acme-api``)
    - ``{{project_module}}`` — Python package name (e.g. ``acme_api``)
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATE_ROOT = PACKAGE_ROOT / "template"

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")

# Files that contain `{{placeholder}}` tokens. The scaffolder re-walks
# the template once per file; for very large projects the cost is negligible.
_TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".json",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".cfg",
    ".ini",
    ".env",
    ".example",
    ".sql",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".sh",
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    "",
}

# Extra user-provided placeholders to expose to the template renderer.
# These are not embedded in the default template; users can adopt them in
# their own custom templates if they need a richer scaffold.
_EXTRA_KEYS = (
    "description",
    "author_name",
    "author_email",
    "license",
    "python_version",
    "rivex_version",
    "version",
    "repository_url",
    "year",
)


def _current_year() -> int:
    import datetime

    return datetime.datetime.now(tz=datetime.timezone.utc).year


@dataclass(frozen=True)
class ScaffoldOptions:
    """Options for :func:`scaffold`.

    Attributes mirror the template placeholders. ``target_dir`` is the output
    directory. ``extras`` allow callers to inject additional ``{{key}}`` values
    for custom templates.
    """

    project_name: str
    target_dir: Path
    description: str = ""
    author_name: str = ""
    author_email: str = ""
    license: str = "MIT"
    version: str = "0.1.0"
    python_version: str = ">=3.10"
    repository_url: str = ""
    year: str = ""
    force: bool = False
    init_git: bool = True
    initial_commit_message: str = "Initial commit — scaffold from rivex"
    install_deps: bool = False
    extras: Mapping[str, str] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return _slugify(self.project_name)

    @property
    def module_name(self) -> str:
        return self.slug.replace("-", "_")

    @property
    def context(self) -> dict[str, str]:
        return {
            "project_name": self.project_name,
            "project_slug": self.slug,
            "project_module": self.module_name,
            "description": self.description or self.project_name,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "license": self.license,
            "version": self.version,
            "python_version": self.python_version,
            "repository_url": self.repository_url,
            "year": self.year or str(_current_year()),
            **self.extras,
        }


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def _isatty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prompt(message: str, *, default: str = "", required: bool = False, validator=None) -> str:
    """Prompt the user on stderr; return their input.

    * ``default`` is shown in brackets and returned if the user just hits Enter.
    * If *required* is True, empty input is rejected and the prompt repeats.
    * *validator* is an optional ``(value) -> str | None`` returning an error
      message for invalid values (which are then re-prompted).
    """
    suffix = f" [{default}]" if default else ""
    while True:
        sys.stdout.write(f"  {message}{suffix}: ")
        sys.stdout.flush()
        try:
            line = sys.stdin.readline()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(1) from None
        value = line.rstrip("\n").rstrip("\r").strip()
        if not value:
            if default:
                value = default
            elif required:
                print("  (a value is required)")
                continue
            else:
                return ""
        if validator is not None:
            err = validator(value)
            if err is not None:
                print(f"  ({err})")
                continue
        return value


def _prompt_yes_no(message: str, *, default_yes: bool = True) -> bool:
    """Prompt a yes/no question; return the boolean answer."""
    hint = "[Y/n]" if default_yes else "[y/N]"
    while True:
        sys.stdout.write(f"  {message} {hint}: ")
        sys.stdout.flush()
        try:
            line = sys.stdin.readline()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(1) from None
        value = line.strip().lower()
        if not value:
            return default_yes
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("  (please answer y or n)")


def _git_user() -> tuple[str, str]:
    """Return the global git ``(user.name, user.email)`` or empty strings."""
    if not _git_available():
        return "", ""
    name = _git("config", "--get", "user.name", cwd=Path.cwd()).stdout.strip()
    email = _git("config", "--get", "user.email", cwd=Path.cwd()).stdout.strip()
    return name, email


def _gather_interactive(
    project_name: str | None,
    target: Path | None,
    *,
    force: bool,
    init_git: bool | None,
    install_deps: bool | None,
) -> ScaffoldOptions:
    """Interactively build a :class:`ScaffoldOptions` from the user."""
    if not _isatty():
        raise RuntimeError(
            "Interactive mode requires a TTY. Pass project_name as an argument "
            "(e.g. `rivex generate 'My App' .`) for non-interactive use."
        )

    print()
    print("  ┌─ Rivex project generator ─────────────────────────")
    print("  │ Press Enter to accept the default shown in [brackets].")
    print("  └────────────────────────────────────────────────────")
    print()

    if not project_name:
        project_name = _prompt("Project name", required=True)
    assert project_name is not None

    default_target = (Path.cwd() / _slugify(project_name)).resolve()
    target_raw = (
        str(target)
        if target
        else _prompt(
            "Output directory",
            default=str(default_target),
        )
    )
    target_path = Path(target_raw).expanduser()

    description = _prompt("Short description", default=project_name)

    default_name, default_email = _git_user()
    author_name = _prompt("Author name", default=default_name, required=True)
    author_email = _prompt(
        "Author email",
        default=default_email,
        required=True,
        validator=_validate_email,
    )

    license_name = _prompt("License", default="MIT")

    version = _prompt("Version", default="0.1.0")
    repository_url = _prompt("Repository URL (optional)", default="")
    python_version = _prompt("Python version constraint", default=">=3.10")

    if init_git is None:
        init_git = _prompt_yes_no("Initialize a git repository?", default_yes=True)
    if init_git and install_deps is None:
        install_deps = _prompt_yes_no("Install dependencies into a .venv now?", default_yes=False)
    # If the user skipped git init we never asked about deps, so
    # default to "don't install" rather than leaving it as ``None``.
    if install_deps is None:
        install_deps = False

    if init_git:
        default_msg = "Initial commit — scaffold from rivex"
        initial_commit_message = _prompt("Initial commit message", default=default_msg)
    else:
        initial_commit_message = ""

    return ScaffoldOptions(
        project_name=project_name,
        target_dir=target_path,
        description=description,
        author_name=author_name,
        author_email=author_email,
        license=license_name,
        version=version,
        python_version=python_version,
        repository_url=repository_url,
        force=force,
        init_git=init_git,
        initial_commit_message=initial_commit_message,
        install_deps=install_deps,
    )


def _slugify(value: str) -> str:
    """Lowercase, replace non-alphanumeric runs with ``-``, trim dashes."""
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)
    return slug.strip("-") or "project"


def _validate_email(value: str) -> str | None:
    """Return an error message if *value* is not a syntactically valid email, else ``None``."""
    if not value or "@" not in value:
        return "must contain '@'"
    local, _, domain = value.partition("@")
    if not local or not domain or "." not in domain:
        return "must be a valid email address"
    return None


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _git_available() -> bool:
    return shutil.which("git") is not None


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_git(
    target: Path, *, user_name: str, user_email: str, initial_message: str
) -> tuple[bool, str]:
    """Initialise a git repo in *target* and create a first commit.

    Returns ``(ok, summary)``. Falls back to a no-op (with a warning) if
    ``git`` is not on ``$PATH`` or if any step fails.
    """
    if not _is_git_repo(target):
        if not _git_available():
            return False, "git executable not found on $PATH — skipping git init"
        result = _git("init", "--initial-branch=main", cwd=target)
        if result.returncode != 0:
            return False, f"git init failed: {result.stderr.strip() or 'unknown error'}"

    # Always set local user identity (does not mutate global config).
    _git("config", "user.name", user_name, cwd=target)
    _git("config", "user.email", user_email, cwd=target)

    result = _git("add", "-A", cwd=target)
    if result.returncode != 0:
        return False, f"git add failed: {result.stderr.strip() or 'unknown error'}"

    result = _git("commit", "-m", initial_message, cwd=target)
    if result.returncode != 0:
        return False, f"git commit failed: {result.stderr.strip() or 'unknown error'}"

    return True, "git repo initialised, files staged and committed"


def _setup_venv(target: Path) -> tuple[bool, str]:
    """Create a ``.venv`` and install the project in editable mode with dev extras."""
    if not (target / "pyproject.toml").is_file():
        return False, "pyproject.toml not found — skipping install"

    venv_dir = target / ".venv"
    if venv_dir.exists():
        return True, ".venv already exists — skipping install"

    import venv  # stdlib

    try:
        builder = venv.EnvBuilder(with_pip=True, upgrade_deps=True, clear=True)
        builder.create(str(venv_dir))
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"failed to create virtualenv: {exc}"

    if sys.platform == "win32":
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        pip = venv_dir / "bin" / "pip"

    if not pip.exists():
        return False, f"pip not found inside {venv_dir}"

    result = subprocess.run(
        [str(pip), "install", "-e", ".[dev]"],
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, f"pip install failed: {(result.stderr or result.stdout).strip()[-500:]}"

    rel = venv_dir.relative_to(target)
    return True, f"virtualenv ready at ./{rel} and project installed in editable mode"


def render(text: str, context: Mapping[str, str]) -> str:
    """Replace ``{{key}}`` placeholders in *text* using *context*."""
    return _PLACEHOLDER_RE.sub(lambda m: str(context[m.group(1)]), text)


def _render_path(template_path: Path, context: Mapping[str, str]) -> str:
    """Render a template *path* (e.g. file/dir names) with placeholders."""
    return render(str(template_path), context)


def _iter_template_files(root: Path):
    """Yield all files under *root* (skipping pycache / hidden noise)."""
    skip_dirs = {"__pycache__", ".git", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
    for entry in root.rglob("*"):
        if entry.is_dir():
            continue
        rel = entry.relative_to(root)
        if any(part in skip_dirs for part in rel.parts):
            continue
        if any(
            part.startswith(".") and part not in {".env.example", ".gitignore"}
            for part in rel.parts
        ):
            continue
        yield entry


def _copy_tree(
    src: Path,
    dst: Path,
    context: Mapping[str, str],
) -> list[Path]:
    """Copy the entire *src* tree into *dst*, rendering placeholders along the way.

    Returns the list of files that were created.
    """
    created: list[Path] = []
    for src_file in _iter_template_files(src):
        rel = src_file.relative_to(src)
        rel_str = _render_path(rel, context)
        target = dst / rel_str
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw = src_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            shutil.copy2(src_file, target)
            created.append(target)
            continue
        rendered = render(raw, context)
        target.write_text(rendered, encoding="utf-8")
        created.append(target)
    return created


def scaffold(options: ScaffoldOptions, template_root: Path | None = None) -> list[Path]:
    """Generate a new Rivex backend project at *options.target_dir*.

    Returns the list of files written. Raises :class:`FileExistsError` if the
    target directory already contains files and ``options.force`` is not set.
    Raises :class:`ValueError` if *options.project_name* is empty.
    """
    if not options.project_name or not options.project_name.strip():
        raise ValueError("project_name must not be empty")

    root = template_root or TEMPLATE_ROOT
    if not root.is_dir():
        raise RuntimeError(f"Scaffold template not found: {root}")

    target = options.target_dir.resolve()
    preserved_env_text: str | None = None
    if target.exists() and any(target.iterdir()):
        if not options.force:
            raise FileExistsError(
                f"Target directory is not empty: {target} (pass --force to overwrite)"
            )
        existing_env = target / ".env"
        if existing_env.is_file():
            # Snapshot the contents before the destructive rmtree below.
            preserved_env_text = existing_env.read_text(encoding="utf-8")
        shutil.rmtree(target)

    target.mkdir(parents=True, exist_ok=True)
    created = _copy_tree(root, target, options.context)

    # Always create a working .env alongside the example. User-local secrets
    # are never clobbered: if we captured an existing .env above, restore it
    # verbatim. Otherwise seed .env from the rendered .env.example.
    env_example = target / ".env.example"
    env_file = target / ".env"
    if env_example.is_file() and not env_file.exists():
        if preserved_env_text is not None:
            env_file.write_text(preserved_env_text, encoding="utf-8")
        else:
            env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        created.append(env_file)

    return created


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rivex generate",
        description=(
            "Generate a new Rivex backend project from the layered template. "
            "Run with no flags to enter interactive mode; pass all flags for "
            "non-interactive use."
        ),
    )
    parser.add_argument(
        "project_name",
        nargs="?",
        default=None,
        help="Human-readable project name (e.g. 'Acme API'). If omitted, the CLI runs interactively.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Target directory (default: <cwd>/<slug>).",
    )
    parser.add_argument(
        "--path",
        dest="path",
        default=None,
        help="Output directory (alias for positional <target>).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite a non-empty target directory.",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Skip git init even when running non-interactively.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Create a .venv and install the project after scaffolding.",
    )
    parser.add_argument(
        "--description",
        default="",
        help="Project description (used in pyproject and README).",
    )
    parser.add_argument(
        "--author-name",
        default="",
        help="Author name (used in pyproject and git config).",
    )
    parser.add_argument(
        "--author-email",
        default="",
        help="Author email (used in pyproject and git config).",
    )
    parser.add_argument(
        "--license",
        default="MIT",
        help="SPDX license identifier (default: MIT).",
    )
    parser.add_argument(
        "--version",
        dest="proj_version",
        default="0.1.0",
        help="Initial project version (default: 0.1.0).",
    )
    parser.add_argument(
        "--repo",
        dest="repository_url",
        default="",
        help="Repository URL (used in pyproject).",
    )
    parser.add_argument(
        "--python",
        dest="python_version",
        default=">=3.10",
        help="Python version constraint (default: >=3.10).",
    )
    parser.add_argument(
        "--commit-message",
        default="Initial commit — scaffold from rivex",
        help="Initial git commit message (default: 'Initial commit — scaffold from rivex').",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Fail instead of prompting when info is missing.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Accept defaults for all interactive prompts.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``rivex generate``."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    target_raw = args.path or args.target
    target = Path(target_raw).expanduser() if target_raw else None

    interactive = args.project_name is None or (
        target is None and not args.no_interactive and _isatty()
    )
    if interactive and not args.no_interactive:
        if args.yes and not args.project_name:
            print("Error: --yes requires an explicit project name", file=sys.stderr)
            return 2
        options = _gather_interactive(
            project_name=args.project_name,
            target=target,
            force=args.force,
            init_git=None if not args.no_git else False,
            install_deps=True if args.install else (False if args.yes else None),
        )
    else:
        if not args.project_name:
            print("Error: project_name is required in non-interactive mode", file=sys.stderr)
            return 2
        resolved_target = target or (Path.cwd() / _slugify(args.project_name))
        if resolved_target.exists() and resolved_target.is_dir() and not args.force:
            resolved_target = resolved_target / _slugify(args.project_name)
        options = ScaffoldOptions(
            project_name=args.project_name,
            target_dir=resolved_target,
            description=args.description or args.project_name,
            author_name=args.author_name,
            author_email=args.author_email,
            license=args.license,
            version=args.proj_version,
            python_version=args.python_version,
            repository_url=args.repository_url,
            force=args.force,
            init_git=not args.no_git,
            initial_commit_message=args.commit_message,
            install_deps=args.install,
        )

    print()
    print(f"  Generating '{options.project_name}' at {options.target_dir} ...")
    try:
        created = scaffold(options)
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"  Created {len(created)} files.")

    git_summary: str | None = None
    git_ok = True
    if options.init_git:
        git_ok, git_summary = _run_git(
            options.target_dir,
            user_name=options.author_name or "Rivex User",
            user_email=options.author_email or "user@example.com",
            initial_message=options.initial_commit_message,
        )
        prefix = "  Git: " if git_ok else "  Git: (warning) "
        print(f"{prefix}{git_summary}")

    install_summary: str | None = None
    install_ok = True
    if options.install_deps:
        print("  Installing dependencies (this may take a moment) ...")
        install_ok, install_summary = _setup_venv(options.target_dir)
        prefix = "  Setup: " if install_ok else "  Setup: (warning) "
        print(f"{prefix}{install_summary}")

    print()
    print("  Next steps:")
    print(f"    cd {options.target_dir}")
    print("    # .env was created from .env.example — edit secrets before first run")
    if not options.install_deps:
        print("    make install")
    print("    make dev")
    if options.init_git and git_ok and options.repository_url:
        print(f"    git remote add origin {options.repository_url}")
        print("    git push -u origin main")
    print()
    return 0 if (git_ok and install_ok) else 1


__all__ = [
    "ScaffoldOptions",
    "TEMPLATE_ROOT",
    "main",
    "render",
    "scaffold",
]
