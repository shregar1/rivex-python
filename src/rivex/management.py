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
        pass

    def handle(self, **options: Any) -> str | None:
        raise NotImplementedError

    def run_from_argv(self, argv: list[str]) -> None:
        parser = argparse.ArgumentParser(prog=f"rivex {self.name}", description=self.description or self.help)
        self.add_arguments(parser)
        args, _ = parser.parse_known_args(argv[2:])
        result = self.handle(**vars(args))
        if result:
            print(result)

    def get_version(self) -> str | None:
        return None


def register_command(name: str, command: BaseCommand) -> None:
    _registered_commands[name] = command


def get_command(name: str) -> BaseCommand | None:
    return _registered_commands.get(name)


def get_all_commands() -> dict[str, BaseCommand]:
    return dict(_registered_commands)


def discover_commands(module_path: str = "rivex.management_commands") -> None:
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
        parser.add_argument("name", help="Group name")
        parser.add_argument("--permissions", nargs="*", default=[], help="Permission codenames")

    def handle(self, **options: Any) -> str | None:
        from rivex.permissions import DEFAULT_PERMISSIONS
        name = options["name"]
        perms = options.get("permissions", [])
        DEFAULT_PERMISSIONS[name] = set(perms)
        return f"Group '{name}' created with permissions: {', '.join(perms) if perms else 'none'}"


class ListGroupsCommand(BaseCommand):
    name = "listgroups"
    help = "List all permission groups"

    def handle(self, **options: Any) -> str | None:
        from rivex.permissions import DEFAULT_PERMISSIONS
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
        parser.add_argument("--input", default="static/", help="Input static directory")
        parser.add_argument("--output", default="staticfiles/", help="Output directory")

    def handle(self, **options: Any) -> str | None:
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
        parser.add_argument("--locale", "-l", required=True, help="Locale code (e.g. fr)")
        parser.add_argument("--input-dir", default=".", help="Source directory")
        parser.add_argument("--output-dir", default="locale", help="Output locale directory")
        parser.add_argument("--domain", default="messages", help="Gettext domain")

    def handle(self, **options: Any) -> str | None:
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
        parser.add_argument("--input-dir", default="locale", help="Locale directory")
        parser.add_argument("--domain", default="messages", help="Gettext domain")

    def handle(self, **options: Any) -> str | None:
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
