from __future__ import annotations

import argparse
import importlib
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rivex", description="Rivex CLI")
    sub = parser.add_subparsers(dest="command")

    # ── serve ──

    # `rivex dev main:app` — local development with autoreload.
    # Built on uvicorn + watchfiles (the same stack `fastapi dev`
    # uses), so you get reliable, fast file-change detection without
    # shelling out to subprocesses.
    dev_parser = sub.add_parser(
        "dev",
        help="Run the app in development mode with autoreload (uvicorn + watchfiles).",
    )
    dev_parser.add_argument("app", help="App import path (e.g. main:app)")
    dev_parser.add_argument("--host", default="127.0.0.1")
    dev_parser.add_argument("--port", type=int, default=8000)
    dev_parser.add_argument(
        "--reload-dir",
        action="append",
        default=None,
        help="Directory to watch for changes (default: the current directory). "
        "May be passed multiple times.",
    )
    dev_parser.add_argument(
        "--no-reload", action="store_true", help="Disable autoreload (debug-only)"
    )
    dev_parser.add_argument("--log-level", default="info", help="uvicorn log level (default: info)")

    # `rivex run main:app` — production-style serve on uvicorn.
    # No autoreload by default; pass --reload for the dev path
    # (or use `rivex dev` instead).
    run_parser = sub.add_parser(
        "run",
        help="Serve the app with uvicorn (production-style, optional --workers).",
    )
    run_parser.add_argument("app", help="App import path (e.g. main:app)")
    run_parser.add_argument("--host", default="127.0.0.1")
    run_parser.add_argument("--port", type=int, default=8000)
    run_parser.add_argument(
        "--workers", type=int, default=1, help="Number of uvicorn worker processes"
    )
    run_parser.add_argument("--reload", action="store_true", help="Enable autoreload (dev only)")
    # `--mode` is the new canonical knob for selecting the engine.
    # The legacy `--sync` and `--asgi` flags still work as aliases of
    # `--mode sync` and `--mode asgi` respectively.
    run_parser.add_argument(
        "--mode",
        choices=["auto", "async", "sync", "asgi"],
        default="auto",
        help="Server engine to use. "
        "'auto' (default) and 'async' both use the bundled Rust "
        "async server (hyper+Tokio) for HTTP/1+HTTP/2, streaming "
        "and websockets. 'sync' uses the bundled Rust std::thread "
        "server (lower per-request latency on CPU-bound handlers; "
        "no streaming, no HTTP/2). 'asgi' uses uvicorn (ASGI 3) for "
        "drop-in FastAPI/Starlette compatibility.",
    )
    run_parser.add_argument(
        "--sync",
        action="store_true",
        help="Alias for --mode sync. Kept for back-compat.",
    )
    run_parser.add_argument(
        "--asgi",
        action="store_true",
        help="Alias for --mode asgi. Kept for back-compat.",
    )
    # `--fast` mirrors Robyn's preset: it auto-tunes the engine for
    # production-like defaults. It can be combined with --mode to
    # pick the engine, e.g. ``--fast --mode sync`` or
    # ``--fast --mode async``. We apply it after parsing so the
    # individual ``--workers`` / ``--log-level`` flags still win
    # when the user passes them explicitly.
    run_parser.add_argument(
        "--fast",
        action="store_true",
        help="Production preset: bumps workers to 2*CPU+1 and "
        "log-level to WARNING. Same idea as Robyn's ``--fast``.",
    )

    # rivex routes
    routes_parser = sub.add_parser("routes", help="List registered routes")
    routes_parser.add_argument("app", help="App import path (e.g. main:app)")

    # rivex version
    sub.add_parser("version", help="Show Rivex version")

    # rivex createsuperuser — Django-style admin user minting. Lives in
    # the core CLI so users with only the bare-bones install can run
    # it.  Delegates to the ``rivex_admin`` companion package; if it's
    # not installed we print a clear "pip install rivex[admin]" hint.
    sub.add_parser(
        "createsuperuser",
        help="Create a new admin dashboard user (interactive).",
        add_help=False,
    )

    # rivex admin — subcommand tree (mint/rotate/list/delete).
    # The handler lazily imports rivex_admin.cli; we just register
    # the subparser shape here so ``rivex admin --help`` works.
    admin_p = sub.add_parser(
        "admin",
        help="Manage admin dashboard users (mint, rotate, list, delete).",
        add_help=False,
    )
    admin_sub = admin_p.add_subparsers(dest="admin_command")
    admin_sub.add_parser("mint", help="Create a new admin user")
    admin_sub.add_parser("list", help="List all admin users")
    admin_sub.add_parser("rotate", help="Replace a user's token")
    admin_sub.add_parser("delete", help="Remove an admin user")

    # rivex generate — scaffold a new layered Rivex backend project.
    sub.add_parser(
        "generate",
        help="Generate a new Rivex backend from the layered template (alias: `new`)",
        add_help=False,
    )
    sub.add_parser(
        "new",
        help="Alias for `rivex generate`",
        add_help=False,
    )

    # rivex schemax — Schemax IDL toolchain (now lives in the standalone
    # `schemax` package as `schemax.idl`). Forwards remaining args.
    sub.add_parser(
        "schemax",
        help="Schemax IDL toolchain (compile, check, fmt, inspect) — runs `schemax idl`",
        add_help=False,
    )

    # rivex management commands — discovered from management_commands/
    mgmt_sub = sub.add_parser(
        "management",
        help="Run management commands (e.g. collectstatic, makemigrations).",
        add_help=False,
    )
    mgmt_sub.add_argument(
        "mgmt_args",
        nargs=argparse.REMAINDER,
        help="Management command name and arguments",
    )

    # rivex test — run tests with pytest + optional coverage reporting.
    test_parser = sub.add_parser(
        "test",
        help="Run the test suite with pytest and optional coverage reporting.",
        add_help=False,
    )
    test_parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Arguments forwarded to pytest (e.g. tests/ --cov=myapp --cov-report=html)",
    )

    if argv is None:
        argv = sys.argv[1:]
    if len(argv) >= 1 and argv[0] in {"generate", "new"}:
        # ``rivex_scaffold`` is an optional companion package. Install
        # with ``pip install rivex[scaffold]`` to use ``rivex generate``.
        try:
            from rivex_scaffold import main as scaffold_main
        except ImportError:
            print(
                "Error: `rivex generate` requires the optional "
                "`rivex_scaffold` package. Install it with: "
                "pip install rivex[scaffold]",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        raise SystemExit(scaffold_main(argv[1:]))
    if len(argv) >= 1 and argv[0] == "createsuperuser":
        # Works without rivex_admin being installed — we point the
        # user at the install command if the store is unavailable.
        from rivex_admin.cli import cmd_createsuperuser

        ns = argparse.Namespace(db=None)
        raise SystemExit(cmd_createsuperuser(ns))
    if len(argv) >= 1 and argv[0] == "admin":
        # ``rivex admin mint/rotate/list/delete`` — fully delegated to
        # the rivex_admin companion package.
        try:
            from rivex_admin.cli import main as admin_cli_main
        except ImportError:
            print(
                "Error: `rivex admin` requires the optional `rivex_admin` "
                "package. Install it with: pip install rivex[admin]",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        raise SystemExit(admin_cli_main(argv[1:]))
    if len(argv) >= 1 and argv[0] == "schemax":
        try:
            from schemax.idl.cli import main as schemax_main
        except ImportError:
            print(
                "Error: `rivex schemax` now requires the `schemax` package. "
                "Install with: pip install schemax",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        raise SystemExit(schemax_main(argv[1:]))
    if len(argv) >= 1 and argv[0] == "test":
        _run_test(argv[1:])
        return

    args = parser.parse_args(argv)

    if args.command == "management":
        _run_management(args.mgmt_args)
    elif args.command == "dev":
        _run_dev(args)
    elif args.command == "run":
        app = _import_app(args.app)
        # Resolve --mode in the face of legacy --sync / --asgi overrides.
        # The legacy flags win for back-compat: a long-standing user
        # with ``rivex run main:app --sync`` in CI should still get the
        # sync engine.
        mode = args.mode
        if getattr(args, "sync", False):
            mode = "sync"
        elif getattr(args, "asgi", False):
            mode = "asgi"
        # ``--fast`` auto-tunes the worker count. We only apply the
        # default when the user didn't pass ``--workers`` explicitly,
        # so an explicit ``--workers 2`` is preserved.
        workers = args.workers
        if getattr(args, "fast", False) and workers <= 1:
            try:
                import os as _os

                cpu = max(1, _os.cpu_count() or 1)
                workers = 2 * cpu + 1
                print(
                    f"  --fast preset: workers={workers} (2*CPU+1, "
                    f"based on {cpu} CPUs)"
                )
            except Exception:
                pass
        if mode in ("auto", "async"):
            app.run_async(host=args.host, port=args.port, workers=workers)
        elif mode == "sync":
            app.run_sync(host=args.host, port=args.port, workers=workers)
        elif mode == "asgi":
            app.run(
                host=args.host,
                port=args.port,
                workers=workers,
                reload=getattr(args, "reload", False),
            )
        else:  # pragma: no cover — argparse guards the choices
            raise SystemExit(f"unknown mode: {mode!r}")
    elif args.command == "routes":
        app = _import_app(args.app)
        _print_routes(app)
    elif args.command == "version":
        from rivex import __version__

        print(f"Rivex {__version__}")
    else:
        parser.print_help()


def _import_app(path: str):
    if ":" not in path:
        print(f"Error: app path must be 'module:variable' (got '{path}')", file=sys.stderr)
        sys.exit(1)
    module_path, attr = path.rsplit(":", 1)
    sys.path.insert(0, ".")
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        print(f"Error: could not import '{module_path}': {e}", file=sys.stderr)
        sys.exit(1)
    app = getattr(module, attr, None)
    if app is None:
        print(f"Error: '{module_path}' has no attribute '{attr}'", file=sys.stderr)
        sys.exit(1)
    return app


def _run_management(mgmt_args: list[str]) -> None:
    """Run a management command by name."""
    from rivex.management import _registered_commands, discover_commands

    discover_commands()

    if not mgmt_args or not mgmt_args[0]:
        print("Available management commands:")
        for name in sorted(_registered_commands):
            print(f"  {name}")
        return

    cmd_name = mgmt_args[0]
    cmd = _registered_commands.get(cmd_name)
    if cmd is None:
        print(f"Unknown management command: {cmd_name}")
        print("Available commands:")
        for name in sorted(_registered_commands):
            print(f"  {name}")
        return

    import sys as _sys
    cmd.run_from_argv(["rivex", cmd_name] + mgmt_args[1:])


def _print_routes(app) -> None:
    routes = getattr(app, "_routes", [])
    if not routes:
        print("No routes registered.")
        return

    method_w = max(len(r.method) for r in routes)
    path_w = max(len(r.path) for r in routes)

    print(f"{'METHOD':<{method_w}}  {'PATH':<{path_w}}  HANDLER")
    print(f"{'─' * method_w}  {'─' * path_w}  {'─' * 30}")
    for r in routes:
        name = r.endpoint.__name__ if hasattr(r.endpoint, "__name__") else str(r.endpoint)
        tags = f" [{', '.join(r.tags)}]" if r.tags else ""
        print(f"{r.method:<{method_w}}  {r.path:<{path_w}}  {name}{tags}")


def _run_with_reload(app_path: str, host: str, port: int) -> None:
    """Legacy subprocess-based autoreload (kept for backward compat with --reload).

    The new ``rivex dev`` command uses uvicorn's built-in watchfiles
    autoreload which is faster and more reliable than this
    reimplementation.
    """
    import os
    import subprocess
    import time

    def _scan_mtimes(dirs: list[str]) -> dict[str, float]:
        mtimes: dict[str, float] = {}
        skip = {"__pycache__", ".git", "node_modules", ".venv", "venv", ".tox"}
        for d in dirs:
            for root, subdirs, files in os.walk(d):
                subdirs[:] = [s for s in subdirs if s not in skip]
                for f in files:
                    if f.endswith(".py"):
                        fp = os.path.join(root, f)
                        try:
                            mtimes[fp] = os.path.getmtime(fp)
                        except OSError:
                            pass
        return mtimes

    module_part = app_path.split(":")[0]
    watch_dirs = ["."]
    base_dir = module_part.replace(".", os.sep)
    if os.path.isdir(base_dir):
        watch_dirs = [base_dir]

    print(f"  Rivex dev server (reload mode) at http://{host}:{port}")
    print(f"  Watching: {', '.join(watch_dirs)}")

    while True:
        before = _scan_mtimes(watch_dirs)
        cmd = [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0,'.'); "
            f"m=__import__('{module_part}'); app=getattr(m,'{app_path.split(':')[1]}'); "
            f"app.run(host='{host}',port={port})",
        ]
        proc = subprocess.Popen(cmd)
        try:
            while proc.poll() is None:
                time.sleep(1.0)
                after = _scan_mtimes(watch_dirs)
                if after != before:
                    changed = []
                    for k in set(after) | set(before):
                        if after.get(k) != before.get(k):
                            changed.append(os.path.basename(k))
                    print(f"\n  File change detected: {', '.join(changed[:5])}")
                    print("  Reloading...\n")
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    break
        except KeyboardInterrupt:
            proc.terminate()
            proc.wait()
            return


def _run_dev(args: argparse.Namespace) -> None:
    """`rivex dev` — start uvicorn with watchfiles-driven autoreload.

    Same model as ``fastapi dev``: hand the app import path to
    uvicorn as a string, let it import the app fresh on every reload,
    and watch the directories for file changes.
    """
    import uvicorn

    if args.no_reload:
        # Treat as a one-shot `rivex run` (no reload, single worker).
        app = _import_app(args.app)
        app.run(host=args.host, port=args.port, log_level=args.log_level)
        return

    reload_dirs = args.reload_dir or ["."]
    # uvicorn's reload path is happy with an import string. We pass the
    # user's `module:app` directly; uvicorn will re-import it on every
    # change and re-bind `app`.
    print(f"  Rivex dev server  🚀  http://{args.host}:{args.port}")
    print(f"  Watching: {', '.join(reload_dirs)}  (Ctrl+C to quit)")
    print()
    uvicorn.run(
        args.app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=True,
        reload_dirs=reload_dirs,
    )


def _run_test(pytest_args: list[str]) -> None:
    """Run pytest with optional coverage via ``rivex test --cov=...``."""
    try:
        import pytest
    except ImportError:
        print(
            "Error: `rivex test` requires pytest. Install it with: "
            "pip install rivex[dev]",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

    # Default args: enable coverage if --cov is present in user args
    args = list(pytest_args)
    has_cov = any(a.startswith("--cov") for a in args)
    if not has_cov:
        # If no coverage requested, run plain pytest + asyncio mode
        if not any(a.startswith("-x") or a.startswith("--exitfirst") or "-k" in a for a in args):
            args = ["--tb=short", "-q"] + args

    exit_code = pytest.main(args)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
