"""``rivex.flags`` — in-process feature-flag registry."""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = ["FlagContext", "FlagDefinition", "FlagRegistry", "is_enabled", "registry"]


@dataclass
class FlagContext:
    """Evaluation context for feature flags."""

    tenant_id: str | None = None
    user_id: str | None = None
    environment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the context fields as a plain dict.

        Useful when handing the context to the Rust engine, which only
        understands ``str`` keys and basic values.

        Returns:
            Dict containing ``tenant_id``, ``user_id`` and
            ``environment`` exactly as stored on this instance. ``None``
            values are preserved so callers can distinguish "not set"
            from an empty string.
        """
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "environment": self.environment,
        }


@dataclass
class FlagDefinition:
    """Definition of a single feature flag."""

    enabled: bool = False
    percentage_rollout: int | None = None
    environments: list[str] | None = None
    tenant_overrides: dict[str, bool] = field(default_factory=dict)
    user_overrides: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlagDefinition:
        """Build a :class:`FlagDefinition` from a plain mapping.

        Performs shallow validation of ``data`` (it must be a ``dict``)
        and copies the mutable override maps so subsequent mutations of
        the source dict do not leak into the new flag.

        Args:
            data: Mapping with optional keys ``enabled``,
                ``percentage_rollout``, ``environments``,
                ``tenant_overrides`` and ``user_overrides``.

        Returns:
            A new :class:`FlagDefinition` populated from ``data``.

        Raises:
            TypeError: When ``data`` is not a ``dict``.
        """
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        return cls(
            enabled=bool(data.get("enabled", False)),
            percentage_rollout=data.get("percentage_rollout"),
            environments=data.get("environments"),
            tenant_overrides=dict(data.get("tenant_overrides", {})),
            user_overrides=dict(data.get("user_overrides", {})),
        )


class FlagRegistry:
    """In-process registry for feature flag definitions backed by rivex-core Rust engine."""

    def __init__(self) -> None:
        self._flags: dict[str, FlagDefinition] = {}
        self._environment: str = "development"
        self._rust_registry = None
        try:
            from rivex.native._compat import rc as _rc
            if hasattr(_rc, "RustFlagRegistry"):
                self._rust_registry = _rc.RustFlagRegistry()
        except Exception:
            pass

    def set_environment(self, env: str) -> None:
        """Switch the active environment for flag evaluations.

        Updates the in-process environment string used when no explicit
        environment is supplied via the evaluation ``context``, and
        forwards the change to the Rust registry when one is bound.

        Args:
            env: The new environment name (e.g. ``"production"``).
        """
        self._environment = env
        if self._rust_registry is not None:
            self._rust_registry.set_environment(env)

    def set(self, name: str, value: bool | dict[str, Any] | FlagDefinition) -> None:
        """Register or update a feature flag definition.

        Accepts a plain boolean for simple on/off flags, a dict that will
        be parsed by :meth:`FlagDefinition.from_dict`, or a fully-formed
        :class:`FlagDefinition` instance. The new value is stored in the
        Python registry and forwarded to the Rust registry when present.

        Args:
            name: The flag identifier.
            value: Either a boolean, a dict-shaped definition, or an
                existing :class:`FlagDefinition` instance.

        Raises:
            TypeError: When ``value`` is none of the supported types.
        """
        if isinstance(value, bool):
            flag_def = FlagDefinition(enabled=value)
        elif isinstance(value, FlagDefinition):
            flag_def = value
        elif isinstance(value, dict):
            flag_def = FlagDefinition.from_dict(value)
        else:
            raise TypeError(f"Invalid flag value: {value!r}")

        self._flags[name] = flag_def
        if self._rust_registry is not None:
            self._rust_registry.set(
                name,
                flag_def.enabled,
                flag_def.percentage_rollout,
                flag_def.environments,
            )

    def clear(self) -> None:
        """Remove every registered flag from the in-process and Rust registries."""
        self._flags.clear()
        if self._rust_registry is not None:
            self._rust_registry.clear()

    def snapshot(self) -> dict[str, FlagDefinition]:
        """Return a shallow copy of the currently registered flags.

        Returns:
            A new ``dict`` mapping flag names to their
            :class:`FlagDefinition`. Mutating the returned dict does not
            affect the registry.
        """
        return dict(self._flags)

    def is_enabled(
        self,
        name: str,
        context: FlagContext | Mapping[str, Any] | None = None,
    ) -> bool:
        """Evaluate a flag against the supplied (or default) context.

        The decision walks a fixed precedence list: unknown flags always
        return ``False``; environment restrictions short-circuit; then
        per-user overrides, per-tenant overrides, and finally a stable
        percentage rollout based on a CRC32 bucket of
        ``"{name}:{subject}"``. Falls through to ``flag.enabled`` when
        none of the prior rules match.

        Args:
            name: The flag identifier to evaluate.
            context: Optional :class:`FlagContext` or plain mapping
                providing ``user_id``, ``tenant_id`` and ``environment``
                overrides. ``None`` falls back to the registry-level
                environment.

        Returns:
            ``True`` when the flag should be considered on for the
            supplied context, otherwise ``False``.
        """
        if name not in self._flags:
            return False

        flag = self._flags[name]

        if isinstance(context, FlagContext):
            ctx_dict = context.to_dict()
        elif isinstance(context, Mapping):
            ctx_dict = dict(context)
        else:
            ctx_dict = {}

        env = ctx_dict.get("environment") or self._environment

        # 1. Environment restriction
        if flag.environments is not None and env not in flag.environments:
            return False

        # 2. User overrides
        user_id = ctx_dict.get("user_id")
        if user_id and user_id in flag.user_overrides:
            return flag.user_overrides[user_id]

        # 3. Tenant overrides
        tenant_id = ctx_dict.get("tenant_id")
        if tenant_id and tenant_id in flag.tenant_overrides:
            return flag.tenant_overrides[tenant_id]

        # 4. Percentage rollout
        if flag.percentage_rollout is not None:
            subject = user_id or tenant_id or "global"
            bucket = (zlib.crc32(f"{name}:{subject}".encode("utf-8")) % 100)
            return bucket < flag.percentage_rollout

        return flag.enabled


registry = FlagRegistry()


def is_enabled(
    name: str,
    context: FlagContext | Mapping[str, Any] | None = None,
) -> bool:
    """Evaluate a flag against the module-level default registry.

    Convenience wrapper around :meth:`FlagRegistry.is_enabled` bound to
    the process-wide ``registry`` instance. Useful for ad-hoc checks
    in handlers and startup code without having to import the registry
    directly.

    Args:
        name: The flag identifier to evaluate.
        context: Optional :class:`FlagContext` or plain mapping carrying
            ``user_id``, ``tenant_id`` and ``environment`` overrides.

    Returns:
        ``True`` when the flag is on for the supplied context,
        otherwise ``False``.
    """
    return registry.is_enabled(name, context)
