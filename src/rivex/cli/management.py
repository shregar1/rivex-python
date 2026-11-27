from __future__ import annotations

import argparse
import importlib
import inspect
import pkgutil
import sys
from collections.abc import Callable
from typing import Any

_registered_commands: dict[str, BaseCommand] = {}


class CommandError(Exception):
    pass


class BaseCommand:
    name: str = ""
    help: str = ""
    description: str = ""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Register this command's CLI arguments on *parser*.

        Subclasses override this to attach their own
        ``argparse`` arguments. The base implementation is a no-op
        so commands that take no options can skip overriding.

        Args:
            parser: The :class:`argparse.ArgumentParser` dedicated
                to this command. Mutations are visible to the
                caller.
        """
        pass

    def handle(self, **options: Any) -> str | None:
        """Execute the command's body using the parsed *options*.

        Subclasses must override this. The returned string, when
        non-empty, is printed by :meth:`run_from_argv` so users
        see command output in the terminal.

        Args:
            **options: Keyword arguments produced by argparse
                from :meth:`add_arguments`.

        Returns:
            A human-readable status string, or ``None`` to stay
            silent. Subclasses should return ``None`` when they
            have already produced their own output.
        """
        raise NotImplementedError

    def run_from_argv(self, argv: list[str]) -> None:
        """Bind argparse to *argv* and invoke :meth:`handle`.

        Builds a private :class:`argparse.ArgumentParser` using
        this command's ``name`` and ``description``, hands it to
        :meth:`add_arguments`, parses the trailing arguments
        (the command's own name is expected at index 1 of
        *argv*, hence the slice from index 2), and dispatches to
        :meth:`handle`. Any non-empty result from ``handle`` is
        printed to stdout.

        Args:
            argv: The full CLI token vector — typically
                ``["rivex", "command-name", ...]``.
        """
        parser = argparse.ArgumentParser(prog=f"rivex {self.name}", description=self.description or self.help)
        self.add_arguments(parser)
        args, _ = parser.parse_known_args(argv[2:])
        result = self.handle(**vars(args))
        if result:
            print(result)

    def get_version(self) -> str | None:
        """Return the version banner for this command, if any.

        The base implementation returns ``None``, which suppresses
        any version output. Override when the command needs to
        advertise its own version distinct from Rivex's own.

        Returns:
            The version string, or ``None`` if the command does
            not expose one.
        """
        return None


def register_command(name: str, command: BaseCommand) -> None:
    """Register a *command* instance under *name*.

    Args:
        name: The invocation name the user types after
            ``rivex management`` (for example ``"creategroup"``).
        command: An instantiated :class:`BaseCommand` subclass
            ready to handle invocations.
    """
    _registered_commands[name] = command


def get_command(name: str) -> BaseCommand | None:
    """Return the registered command for *name*, or ``None``.

    Args:
        name: The name previously passed to
            :func:`register_command`.

    Returns:
        The :class:`BaseCommand` instance, or ``None`` when no
        command has been registered under that name.
    """
    return _registered_commands.get(name)


def get_all_commands() -> dict[str, BaseCommand]:
    """Return a copy of the global ``{name: command}`` registry.

    Returns:
        A shallow copy of the registry, so callers can iterate
        without observing later registrations or vice versa.
    """
    return dict(_registered_commands)


def discover_commands(module_path: str = "rivex.management_commands") -> None:
    """Import every submodule of *module_path* and register their commands.

    Walks the package at *module_path*, imports each submodule,
    and registers every :class:`BaseCommand` subclass it finds.
    Failures during import are swallowed so a single broken
    command does not prevent discovery of the rest. Missing
    packages (no ``rivex.management_commands`` installed) are a
    silent no-op.

    Args:
        module_path: Dotted import path to the package whose
            submodules should be scanned. Defaults to
            ``rivex.management_commands``.
    """
    try:
        mod = importlib.import_module(module_path)
    except ImportError:
        return
    path = getattr(mod, "__path__", [])
    for finder, name, ispkg in pkgutil.iter_modules(path):
        try:
            module = importlib.import_module(f"{module_path}.{name}")
            for _, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, BaseCommand) and obj is not BaseCommand:
                    cmd_name = obj.name or name.replace("_", "-")
                    register_command(cmd_name, obj())
        except Exception:
            pass


def add_management_subcommands(subparsers) -> None:
    """Hook called from cli.py to register all discovered commands."""
    import rivex.management_commands

    discover_commands()

    for name, cmd in sorted(_registered_commands.items()):
        parser = subparsers.add_parser(name, help=cmd.help, description=cmd.description or cmd.help)
        cmd.add_arguments(parser)
        parser.set_defaults(_cmd_handler=cmd.run_from_argv)


class CreateGroupCommand(BaseCommand):
    name = "creategroup"
    help = "Create a new permission group"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Attach the ``name`` and ``--permissions`` arguments to *parser*."""
        parser.add_argument("name", help="Group name")
        parser.add_argument("--permissions", nargs="*", default=[], help="Permission codenames")

    def handle(self, **options: Any) -> str | None:
        """Create the requested permission group in the auth engine's in-memory registry.

        Args:
            **options: ``name`` (the group name) and an optional
                ``permissions`` list of permission codenames.

        Returns:
            A status string describing what was created.
        """
        from rivex.auth.permissions import DEFAULT_PERMISSIONS
        name = options["name"]
        perms = options.get("permissions", [])
        DEFAULT_PERMISSIONS[name] = set(perms)
        return f"Group '{name}' created with permissions: {', '.join(perms) if perms else 'none'}"


class ListGroupsCommand(BaseCommand):
    name = "listgroups"
    help = "List all permission groups"

    def handle(self, **options: Any) -> str | None:
        """Print every permission group and the codenames it currently grants.

        Args:
            **options: Not used; accepted for the
                :class:`BaseCommand` interface.

        Returns:
            A multi-line listing of groups and their permissions,
            or ``"No groups defined."`` when the registry is empty.
        """
        from rivex.auth.permissions import DEFAULT_PERMISSIONS
        if not DEFAULT_PERMISSIONS:
            return "No groups defined."
        lines: list[str] = []
        for group, perms in sorted(DEFAULT_PERMISSIONS.items()):
            lines.append(f"  {group}: {', '.join(sorted(perms)) if perms else '(no permissions)'}")
        return "Groups:\n" + "\n".join(lines)


class CollectStaticCommand(BaseCommand):
    name = "collectstatic"
    help = "Copy static files to a single output directory"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Attach the ``--input`` and ``--output`` paths to *parser*."""
        parser.add_argument("--input", default="static/", help="Input static directory")
        parser.add_argument("--output", default="staticfiles/", help="Output directory")

    def handle(self, **options: Any) -> str | None:
        """Copy every file under ``--input`` into ``--output`` preserving structure.

        Missing input directories are reported instead of erroring
        so the command is safe to run before any static assets
        exist. The output directory and any missing intermediate
        parents are created on demand.

        Args:
            **options: ``input`` and ``output`` paths.

        Returns:
            A summary of how many files were copied.
        """
        import shutil
        from pathlib import Path

        src = Path(options["input"])
        dst = Path(options["output"])
        if not src.exists():
            return f"Input directory '{src}' does not exist."
        dst.mkdir(parents=True, exist_ok=True)
        count = 0
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                count += 1
        return f"Copied {count} files from '{src}' to '{dst}'."


class MakeMessagesCommand(BaseCommand):
    name = "makemessages"
    help = "Extract translatable strings from source files"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Attach the locale/source/output/domain flags to *parser*."""
        parser.add_argument("--locale", "-l", required=True, help="Locale code (e.g. fr)")
        parser.add_argument("--input-dir", default=".", help="Source directory")
        parser.add_argument("--output-dir", default="locale", help="Output locale directory")
        parser.add_argument("--domain", default="messages", help="Gettext domain")

    def handle(self, **options: Any) -> str | None:
        """Run ``xgettext`` / ``msgmerge`` to refresh the project's ``.po`` catalog.

        Builds an empty ``.pot`` template if ``xgettext`` did not
        produce one, then either merges the new template into an
        existing per-locale ``.po`` (via ``msgmerge``) or copies
        the template in place as a fresh catalog. The gettext
        binaries (``xgettext``, ``msgmerge``) must be on ``PATH``.

        Args:
            **options: ``locale``, ``output_dir``, ``domain``, and
                ``input_dir``.

        Returns:
            A status string indicating whether the catalog was
            updated or newly created.
        """
        import subprocess
        from pathlib import Path

        locale = options["locale"]
        output_dir = Path(options["output_dir"])
        domain = options["domain"]
        input_dir = Path(options["input_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        pot_path = output_dir / f"{domain}.pot"
        po_path = output_dir / locale / "LC_MESSAGES" / f"{domain}.po"

        result = subprocess.run(
            ["xgettext", "--language=Python", "--from-code=UTF-8", f"--output={pot_path}",
             "--keyword=_", "--keyword=gettext", "--keyword=ngettext:1,2",
             f"--files-from=/dev/stdin"],
            input="", capture_output=True, text=True
        )

        if not pot_path.exists():
            with open(pot_path, "w") as f:
                f.write(f'# {domain}.pot\n# AUTO-GENERATED\n\n')

        po_path.parent.mkdir(parents=True, exist_ok=True)
        if po_path.exists():
            subprocess.run(["msgmerge", "--update", str(po_path), str(pot_path)])
            return f"Updated {po_path} from template."
        else:
            shutil.copy2(pot_path, po_path)
            return f"Created {po_path}. Edit it to add translations."


class CompileMessagesCommand(BaseCommand):
    name = "compilemessages"
    help = "Compile .po files to .mo binaries"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Attach the ``--input-dir`` and ``--domain`` flags to *parser*."""
        parser.add_argument("--input-dir", default="locale", help="Locale directory")
        parser.add_argument("--domain", default="messages", help="Gettext domain")

    def handle(self, **options: Any) -> str | None:
        """Compile every ``.po`` file in the locale directory into ``.mo`` binaries.

        Uses the external ``msgfmt`` binary; a missing locale
        directory is reported but not treated as fatal so the
        command is safe to run before catalogs exist.

        Args:
            **options: ``input_dir`` and ``domain`` controlling
                which ``.po`` files are matched.

        Returns:
            A summary of how many ``.po`` files were compiled.
        """
        import subprocess
        from pathlib import Path

        input_dir = Path(options["input_dir"])
        domain = options["domain"]
        if not input_dir.exists():
            return f"Locale directory '{input_dir}' not found."

        count = 0
        for po_path in input_dir.rglob(f"{domain}.po"):
            mo_path = po_path.with_suffix(".mo")
            subprocess.run(["msgfmt", str(po_path), "-o", str(mo_path)])
            count += 1
        return f"Compiled {count} .po files to .mo."
