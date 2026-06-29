"""``rivex admin`` and ``rivex createsuperuser`` subcommands.

Django-style admin user management for the dashboard:

    rivex createsuperuser
        Django-style: prompt for username + token, write to the DB.

    rivex admin mint [--username USER] [--token TOKEN] [--note NOTE]
        Non-interactive mint.  If --token is omitted, generate a
        cryptographically random one and print it once.

    rivex admin list
        List all admin users (id, username, created, last used, note).

    rivex admin rotate <username> [--token TOKEN]
        Replace an existing user's token.  Print the new token once.

    rivex admin delete <username>
        Remove an admin user.

The CLI lives here (in ``rivex_admin``) so it's installed alongside
the dashboard.  ``rivex createsuperuser`` is also wired in the core
``rivex`` CLI as an alias so users with only the bare-bones install
can run it too — it'll just print a clear "install rivex[admin]"
message if the DB module isn't available.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from getpass import getpass
from pathlib import Path
from typing import cast


def _store(path: Path | None):
    from rivex_admin.db import AdminStore

    return AdminStore(path)


def _print_token_once(token: str, username: str) -> None:
    """Show the user the token *exactly once*.  Loud and unmissable."""
    print()
    print("=" * 72)
    print(f"  Admin user:    {username}")
    print(f"  Token (save!): {token}")
    print("=" * 72)
    print("  This token will not be shown again.  Store it in a password")
    print("  manager or paste it into the dashboard's auth header:")
    print()
    print(f'    curl -H "X-Admin-Token: {token}" http://localhost:PORT/admin')
    print()


def cmd_mint(args: argparse.Namespace) -> int:
    """``rivex admin mint`` — non-interactive."""
    store = _store(args.db)
    token = args.token
    if not token:
        from rivex_admin.db import generate_token

        token = generate_token()
        auto_generated = True
    else:
        auto_generated = False

    user = store.add_user(args.username, token, note=args.note)
    if auto_generated:
        _print_token_once(token, user.username)
    else:
        print(f"  Created admin user {user.username!r} (id={user.id}).")
        print("  Token was supplied on the command line; not echoed back.")
    return 0


def cmd_createsuperuser(args: argparse.Namespace) -> int:
    """``rivex createsuperuser`` — Django-style interactive prompt."""
    try:
        from rivex_admin.db import AdminStore
    except ImportError as exc:
        print(
            "Error: `rivex createsuperuser` requires the `rivex_admin` "
            "package (which carries the SQLite store). Install with:\n"
            "    pip install rivex[admin]\n"
            f"({exc})",
            file=sys.stderr,
        )
        return 2

    store = AdminStore(args.db)
    try:
        username = input("Username (default 'admin'): ").strip() or "admin"
        # If a user with this name already exists, refuse — the user
        # probably wants `rivex admin rotate` instead.
        if store.get_user_by_name(username) is not None:
            print(
                f"Error: admin user {username!r} already exists. "
                f"Use `rivex admin rotate {username}` to change the token.",
                file=sys.stderr,
            )
            return 3
        token = getpass("Token (leave blank to auto-generate): ")
        if not token:
            from rivex_admin.db import generate_token

            token = generate_token()
            auto = True
        else:
            # Confirm once — typos in tokens are unrecoverable.
            again = getpass("Token (again): ")
            if token != again:
                print("Error: tokens do not match.", file=sys.stderr)
                return 4
            auto = False
        user = store.add_user(username, token)
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.", file=sys.stderr)
        return 130

    print(f"\n  Created admin user {user.username!r} (id={user.id}).")
    if auto:
        _print_token_once(token, user.username)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = _store(args.db)
    users = store.list_users()
    if not users:
        print("  (no admin users — run `rivex createsuperuser` to mint one)")
        return 0
    name_w = max(len(u.username) for u in users)
    print(f"  {'id':>4}  {'username':<{name_w}}  {'created':<19}  {'last used':<19}  note")
    print(f"  {'─' * 4}  {'─' * name_w}  {'─' * 19}  {'─' * 19}  {'─' * 24}")
    for u in users:
        print(
            f"  {u.id:>4}  {u.username:<{name_w}}  "
            f"{u.created_at:<19}  {(u.last_used_at or '—'):<19}  {u.note or ''}"
        )
    return 0


def cmd_rotate(args: argparse.Namespace) -> int:
    store = _store(args.db)
    if store.get_user_by_name(args.username) is None:
        print(f"Error: no admin user named {args.username!r}.", file=sys.stderr)
        print("Run `rivex admin list` to see existing users.", file=sys.stderr)
        return 1
    token = args.token
    auto = False
    if not token:
        from rivex_admin.db import generate_token

        token = generate_token()
        auto = True
    user = store.rotate_token(args.username, token)
    if auto:
        _print_token_once(token, user.username)
    else:
        print(f"  Rotated token for {user.username!r}.")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    store = _store(args.db)
    if not args.yes:
        confirm = input(f"Delete admin user {args.username!r}? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return 0
    if store.delete_user(args.username):
        print(f"  Deleted admin user {args.username!r}.")
        return 0
    print(f"  No admin user {args.username!r}.", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Argparse setup — both the `rivex admin ...` subcommand tree and the
# top-level `rivex createsuperuser` shortcut.
# ---------------------------------------------------------------------------


def build_admin_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rivex admin",
        description="Manage admin dashboard users (SQLite-backed).",
    )

    def _add_db(p_or_m):
        """``--db`` is a global flag that can sit before OR after the
        subcommand (so users can write either
        ``rivex admin --db /tmp/a.db mint ...`` or
        ``rivex admin mint ... --db /tmp/a.db``).  We register it on
        both the parent and each subparser so argparse accepts either.
        """
        p_or_m.add_argument(
            "--db",
            type=Path,
            default=None,
            help="Path to the admin SQLite DB (default: $RIVEX_ADMIN_DB or ./.rivex/admin.db).",
        )

    _add_db(p)
    sub = p.add_subparsers(dest="admin_command", required=True)

    m = sub.add_parser("mint", help="Create a new admin user")
    _add_db(m)
    m.add_argument("--username", required=True, help="Username (unique)")
    m.add_argument(
        "--token",
        default=None,
        help="Raw token to hash + store.  If omitted, a 256-bit "
        "URL-safe token is generated and printed once.",
    )
    m.add_argument("--note", default=None, help="Optional free-text note")
    m.set_defaults(func=cmd_mint)

    lst = sub.add_parser("list", help="List all admin users")
    _add_db(lst)
    lst.set_defaults(func=cmd_list)

    r = sub.add_parser("rotate", help="Replace an existing user's token")
    _add_db(r)
    r.add_argument("username", help="Username to rotate")
    r.add_argument(
        "--token",
        default=None,
        help="New token.  If omitted, a 256-bit URL-safe token is generated and printed once.",
    )
    r.set_defaults(func=cmd_rotate)

    d = sub.add_parser("delete", help="Remove an admin user")
    _add_db(d)
    d.add_argument("username", help="Username to delete")
    d.add_argument("-y", "--yes", action="store_true", help="Skip the confirmation prompt")
    d.set_defaults(func=cmd_delete)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_admin_parser()
    args = parser.parse_args(argv)
    return cast(int, args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
