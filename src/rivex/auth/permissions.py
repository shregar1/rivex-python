from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

from rivex.lifecycle.events import Signal
from rivex.exceptions.http.exceptions import HTTPException

permission_checked = Signal("permission_checked")
permission_denied = Signal("permission_denied")


@dataclass
class User:
    id: str | int
    username: str
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    is_active: bool = True
    is_superuser: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_perm(self, perm: str) -> bool:
        """Return ``True`` if this user holds ``perm`` via any source.

        Superusers always pass. Otherwise the codename is checked
        against the explicit ``permissions`` list and the union of
        :data:`DEFAULT_PERMISSIONS` entries for every group the user
        belongs to.

        Args:
            perm: Permission codename to look up.

        Returns:
            ``True`` if any of the sources grants ``perm``,
            ``False`` otherwise.
        """
        if self.is_superuser:
            return True
        return perm in self.permissions or any(
            perm in DEFAULT_PERMISSIONS.get(g, set())
            for g in self.groups
        )

    def has_role(self, role: str) -> bool:
        """Return ``True`` if this user holds the named role.

        Superusers always pass. Otherwise ``role`` is compared against
        the user's ``roles`` list.

        Args:
            role: Role name to look up.

        Returns:
            ``True`` if the user has the role, ``False`` otherwise.
        """
        if self.is_superuser:
            return True
        return role in self.roles

    def has_perms(self, *perms: str) -> bool:
        """Return ``True`` only if every named permission is held.

        Short-circuits on the first missing permission.

        Args:
            *perms: Permission codenames to check in order.

        Returns:
            ``True`` when :meth:`has_perm` returns ``True`` for every
            argument, ``False`` otherwise.
        """
        return all(self.has_perm(p) for p in perms)


DEFAULT_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"view", "create", "edit", "delete", "manage"},
    "editor": {"view", "create", "edit"},
    "viewer": {"view"},
}


class Permission:
    """Declarative permission that can be checked against a user."""

    def __init__(self, codename: str, description: str = "", model: str | None = None):
        self.codename = codename
        self.description = description
        self.model = model

    def __repr__(self) -> str:
        return f"Permission({self.codename})"

    def check(self, user: User | None, obj: Any = None) -> bool:
        """Evaluate this permission against ``user``.

        Always returns ``False`` when ``user`` is ``None``; otherwise
        delegates to :meth:`User.has_perm` using this permission's
        ``codename``. The ``obj`` argument is accepted for signature
        compatibility with :class:`ModelPermission` but is ignored here.

        Args:
            user: The user to test, or ``None`` for an anonymous caller.
            obj: Optional object context (unused by this class).

        Returns:
            ``True`` if the user holds the permission, ``False`` otherwise.
        """
        if user is None:
            return False
        return user.has_perm(self.codename)


class ModelPermission(Permission):
    """Permission scoped to a specific model instance."""

    def __init__(self, action: str, model: str, obj: Any = None):
        codename = f"{action}_{model}"
        description = f"Can {action} {model}"
        super().__init__(codename, description, model)
        self.action = action
        self.obj = obj

    def check(self, user: User | None, obj: Any = None) -> bool:
        """Evaluate this model-scoped permission, honoring ownership.

        If a target object is supplied (either as ``obj`` or via
        :attr:`obj`), and the object exposes an ``owner_id`` matching
        the user's id, the check passes without consulting the
        permission codename. Otherwise the underlying
        :meth:`User.has_perm` lookup is used.

        Args:
            user: The user to test, or ``None``.
            obj: Optional object instance; overrides the one bound at
                construction time when provided.

        Returns:
            ``True`` if the user is the owner, holds the model
            permission, or both, ``False`` otherwise.
        """
        if user is None:
            return False
        target = obj or self.obj
        if target is not None:
            owner_id = getattr(target, "owner_id", None)
            if owner_id is not None and str(owner_id) == str(user.id):
                return True
        return user.has_perm(self.codename)


class ObjectPermissionBackend:
    """Check per-object permissions (e.g. row-level security)."""

    def has_perm(self, user: User, perm: str, obj: Any) -> bool:
        """Return ``True`` when ``user`` holds ``perm`` for ``obj`` (abstract)."""
        raise NotImplementedError

    def get_perms(self, user: User, obj: Any) -> list[str]:
        """Return the full set of permission codenames ``user`` holds for ``obj``."""
        raise NotImplementedError


class RoleBasedBackend(ObjectPermissionBackend):
    def has_perm(self, user: User, perm: str, obj: Any) -> bool:
        """Return ``True`` if any of ``user``'s roles grants ``perm``.

        Looks ``perm`` up in :data:`DEFAULT_PERMISSIONS` for every role
        the user holds. The ``obj`` argument is accepted for signature
        compatibility but is not consulted by this backend.

        Args:
            user: The user to test.
            perm: Permission codename to look up.
            obj: Optional object context (unused).

        Returns:
            ``True`` when at least one role grants ``perm``,
            ``False`` otherwise.
        """
        for role in user.roles:
            perms = DEFAULT_PERMISSIONS.get(role, set())
            if perm in perms:
                return True
        return False

    def get_perms(self, user: User, obj: Any) -> list[str]:
        """Return the union of all default permissions for the user's roles.

        The ``obj`` argument is accepted for signature compatibility but
        is not consulted by this backend.

        Args:
            user: The user whose permissions are being collected.
            obj: Optional object context (unused).

        Returns:
            A deduplicated list of permission codenames granted by the
            user's roles.
        """
        result: list[str] = []
        for role in user.roles:
            result.extend(DEFAULT_PERMISSIONS.get(role, set()))
        return list(set(result))


_permission_backends: list[ObjectPermissionBackend] = [RoleBasedBackend()]
_registered_permissions: dict[str, Permission] = {}


def register_permission_backend(backend: ObjectPermissionBackend) -> None:
    """Append ``backend`` to the list consulted by every permission check.

    The new backend is tried in registration order after the built-in
    :class:`RoleBasedBackend` and any backends registered earlier.
    There is no deduplication, so registering the same backend twice
    causes its checks to run twice.

    Args:
        backend: An :class:`ObjectPermissionBackend` instance to add
            to the global registry.
    """
    _permission_backends.append(backend)


def register_permission(perm: Permission) -> None:
    """Register ``perm`` in the global permission lookup table.

    Stored under ``perm.code`` (note: not ``codename``); the mapping is
    used by helper APIs that need to resolve a codename back to its
    :class:`Permission` object.

    Args:
        perm: The :class:`Permission` instance to register.
    """
    _registered_permissions[perm.code] = perm


class _PermissionDenied(Exception):
    def __init__(self, permission: str, user: User | None = None):
        self.permission = permission
        self.user = user
        super().__init__(f"Permission denied: {permission}")


def permission_required(
    perm: str | Permission,
    raise_exception: bool = True,
) -> Callable:
    """Decorator that checks a permission before allowing access.

    Usage::

        @app.get("/admin")
        @permission_required("view_admin")
        async def admin_panel(request): ...

    The current user must be set via ``set_user_resolver()``
    (see :mod:`rivex.auth`).
    """
    perm_codename = perm.codename if isinstance(perm, Permission) else perm

    def decorator(func: Callable) -> Callable:
        """Wrap ``func`` so it only runs when ``current_user()`` has the permission.

        Emits the ``permission_checked`` signal before the lookup and the
        ``permission_denied`` signal when the check fails. When
        ``raise_exception`` is true (default), a failure raises a 403
        :class:`HTTPException`; otherwise the wrapper simply returns
        ``None`` and the handler is not awaited.

        Args:
            func: The async handler to guard.

        Returns:
            A coroutine function that performs the permission check and
            then delegates to ``func`` on success.
        """
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Run the permission check, then delegate to the wrapped handler.

            Reads the current user via :func:`current_user`, fires the
            ``permission_checked`` signal, and queries every registered
            permission backend. On failure, fires ``permission_denied``
            and either raises ``HTTPException(403)`` or returns
            ``None`` based on ``raise_exception``.

            Args:
                *args: Positional arguments forwarded to the handler.
                **kwargs: Keyword arguments forwarded to the handler.

            Returns:
                The wrapped handler's return value, or ``None`` when
                the check fails and ``raise_exception`` is false.

            Raises:
                HTTPException: With status 403 when the check fails and
                    ``raise_exception`` is true.
            """
            from rivex.auth.auth import current_user

            user = current_user()
            permission_checked.send(sender=func, user=user, permission=perm_codename)
            if user is None or not any(
                backend.has_perm(user, perm_codename, None)
                for backend in _permission_backends
            ):
                permission_denied.send(sender=func, user=user, permission=perm_codename)
                if raise_exception:
                    raise HTTPException(403, detail=f"Permission denied: {perm_codename}")
                return None
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def has_permission(user: User | None, perm: str, obj: Any = None) -> bool:
    """Imperative permission check (useful inside route handlers).

    Usage::

        if has_permission(current_user(), "edit_article", article):
            ...
    """
    if user is None:
        return False
    permission_checked.send(sender=None, user=user, permission=perm)
    for backend in _permission_backends:
        if backend.has_perm(user, perm, obj):
            return True
    return False


class PermissionsMiddleware:
    """Middleware that attaches a ``permissions`` helper to request state.

    Usage::

        app.add_middleware(PermissionsMiddleware)
    """

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the downstream chain unchanged.

        This middleware is a placeholder that exists so applications can
        register the permissions package as a middleware without
        altering request handling; per-route enforcement happens
        through :func:`permission_required` and :func:`has_permission`.

        Args:
            request_data: The in-flight request envelope as carried by
                the middleware chain.
            call_next: Awaitable returning the downstream response dict.

        Returns:
            The downstream response dict, unmodified.
        """
        result: dict = await call_next(request_data)
        return result
