from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

from rivex.events import Signal
from rivex.core.exceptions import HTTPException

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
        if self.is_superuser:
            return True
        return perm in self.permissions or any(
            perm in DEFAULT_PERMISSIONS.get(g, set())
            for g in self.groups
        )

    def has_role(self, role: str) -> bool:
        if self.is_superuser:
            return True
        return role in self.roles

    def has_perms(self, *perms: str) -> bool:
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
        raise NotImplementedError

    def get_perms(self, user: User, obj: Any) -> list[str]:
        raise NotImplementedError


class RoleBasedBackend(ObjectPermissionBackend):
    def has_perm(self, user: User, perm: str, obj: Any) -> bool:
        for role in user.roles:
            perms = DEFAULT_PERMISSIONS.get(role, set())
            if perm in perms:
                return True
        return False

    def get_perms(self, user: User, obj: Any) -> list[str]:
        result: list[str] = []
        for role in user.roles:
            result.extend(DEFAULT_PERMISSIONS.get(role, set()))
        return list(set(result))


_permission_backends: list[ObjectPermissionBackend] = [RoleBasedBackend()]
_registered_permissions: dict[str, Permission] = {}


def register_permission_backend(backend: ObjectPermissionBackend) -> None:
    _permission_backends.append(backend)


def register_permission(perm: Permission) -> None:
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
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
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
        result: dict = await call_next(request_data)
        return result
