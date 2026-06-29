"""Plugin base class + entry-point discovery for Rivex.

Rivex is intentionally a *small* core — the HTTP framework, the
request pipeline, the body-coercion layer.  Things that not every
user wants (admin dashboard, codegen, project scaffolder) live in
separate companion packages and advertise themselves through Python
entry points so they can be discovered at runtime without Rivex
having to import them upfront.

Two surfaces here:

* :class:`Plugin` — base class for in-process plugin objects that
  want to install routes, middleware, or hooks on a :class:`Rivex`
  app.  Inherit and call ``app.add_plugin(MyPlugin())``.

* :func:`load_plugins` — read Python entry points under the
  ``rivex.plugins.*`` groups (admin, codegen, scaffold) and return
  the discovered callables.  Built-in companion packages
  (``rivex_admin``, ``rivex_codegen``, ``rivex_scaffold``) and
  third-party packages alike are picked up the same way.

Entry-point groups:

* ``rivex.plugins.admin``    — admin dashboard mount functions.
  Each entry point is a ``register(app, base_path, token)`` callable.
* ``rivex.plugins.codegen``  — resource scaffolders.  Each entry
  point is a ``generate(spec, **kwargs)`` callable.
* ``rivex.plugins.scaffold`` — project scaffolders (CLI command
  adapters).  Each entry point is a ``main(argv) -> int`` callable.

Usage::

    from rivex.plugins import Plugin, load_plugins

    class AuthPlugin(Plugin):
        name = "auth"

        def install(self, app):
            app.add_middleware(AuthMiddleware)

    app.add_plugin(AuthPlugin())

    admin_plugins = load_plugins("rivex.plugins.admin")
    for name, register in admin_plugins.items():
        register(app, base_path="/admin", token=None)
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import metadata
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rivex.applications import Rivex


class Plugin:
    """Base class for in-process Rivex plugins.

    A plugin attaches middleware, routes, or hooks to a
    :class:`Rivex` app at construction time.  Use :meth:`Rivex.add_plugin`
    to register; the app calls :meth:`install` once the framework
    is fully built.

    Usage::

        class AuthPlugin(Plugin):
            name = "auth"

            def install(self, app):
                app.add_middleware(AuthMiddleware)

                @app.get("/login")
                async def login(): ...

        app = Rivex()
        app.add_plugin(AuthPlugin())
    """

    name: str = ""

    def install(self, app: Rivex) -> None:
        raise NotImplementedError

    def uninstall(self, app: Rivex) -> None:
        pass


GROUPS: tuple[str, ...] = (
    "rivex.plugins.admin",
    "rivex.plugins.codegen",
    "rivex.plugins.scaffold",
)


def load_plugins(group: str) -> dict[str, Callable[..., Any]]:
    """Return ``{name: callable}`` for every entry point in *group*.

    Missing entry-point groups return an empty dict.  Plugins that
    fail to import are skipped with a warning so one bad plugin
    doesn't break the rest.
    """
    import warnings

    out: dict[str, Callable[..., Any]] = {}
    try:
        eps = metadata.entry_points()
    except Exception as exc:  # pragma: no cover
        warnings.warn(
            f"rivex.plugins: could not enumerate entry points: {exc}",
            stacklevel=2,
        )
        return out
    selected = eps.select(group=group)
    for ep in selected:
        try:
            out[ep.name] = ep.load()
        except Exception as exc:  # pragma: no cover
            warnings.warn(
                f"rivex.plugins: failed to load `{group}:{ep.name}` — {exc}",
                stacklevel=2,
            )
    return out


__all__ = ["GROUPS", "Plugin", "load_plugins"]
