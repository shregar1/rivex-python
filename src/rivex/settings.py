"""``rivex.settings`` — environment-variable-driven configuration.

Mirrors the ergonomics of ``pydantic-settings`` but built on top of
``rivex.Schema`` so it shares one validator/serializer machinery with
the rest of the SDK. No extra dependency.

Typical use:

.. code-block:: python

    from rivex import Settings

    class AppSettings(Settings):
        database_url: str
        secret_key: str
        debug: bool = False
        port: int = 8000

        model_config = {"env_prefix": "MYAPP_", "env_file": ".env"}

    settings = AppSettings.from_env()

The class-level ``model_config`` dict accepts a few extra keys beyond
the ones documented on :class:`rivex.Schema`:

* ``env_prefix`` (str) — uppercased prefix to look for. With
  ``env_prefix="MYAPP_"``, the ``database_url`` field reads
  ``MYAPP_DATABASE_URL``. Default: empty.
* ``env_file`` (str | path) — optional ``.env`` file to load before
  reading ``os.environ``. The file is line-oriented ``KEY=value``;
  comments start with ``#``. ``os.environ`` always wins on conflicts
  so deployment-time vars override the checked-in ``.env``.
* ``env_nested_delimiter`` (str) — split nested keys on this separator.
  With ``env_nested_delimiter="__"`` and a nested ``Schema`` field
  ``db``, ``MYAPP_DB__HOST=...`` populates ``db.host``. Default:
  ``"__"`` (only consulted when the field is a nested Schema).
* ``case_sensitive`` (bool) — match env var names exactly when ``True``,
  otherwise case-insensitively. Default: ``False`` (matches the
  pydantic-settings default).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar

from rivex.schema import Schema


def _parse_env_file(path: str | os.PathLike[str]) -> dict[str, str]:
    """Lightweight ``.env`` parser — ``KEY=value``, ``#`` comments, no shell evaluation.

    Compatible with the common ``python-dotenv`` syntax for the basics.
    Values are taken verbatim (so quotes are part of the value); strip
    them yourself if you used them for readability in the file.
    """
    parsed: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return parsed
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding single or double quotes — only one layer.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        parsed[key] = value
    return parsed


class Settings(Schema):
    """``Schema`` subclass that builds its values from environment variables.

    Use ``Settings.from_env()`` to construct an instance from a merged
    view of ``os.environ`` plus any ``.env`` file declared in
    ``model_config``. Use ``Settings.from_dict(d)`` to build from an
    arbitrary mapping — useful in tests.
    """

    model_config: ClassVar[dict[str, Any]] = {}

    @classmethod
    def _build_env(cls) -> dict[str, str]:
        """Merge ``.env`` (if any) under ``os.environ``."""
        cfg = cls.model_config or {}
        merged: dict[str, str] = {}
        env_file = cfg.get("env_file")
        if env_file:
            merged.update(_parse_env_file(env_file))
        merged.update(os.environ)
        return merged

    @classmethod
    def _collect_values(cls, env: dict[str, str]) -> dict[str, Any]:
        """Pull field values out of ``env``, honouring prefix + case rules."""
        cfg = cls.model_config or {}
        prefix: str = cfg.get("env_prefix", "")
        case_sensitive: bool = bool(cfg.get("case_sensitive", False))
        nested_delim: str = cfg.get("env_nested_delimiter", "__") or "__"

        if not case_sensitive:
            env_lookup = {k.lower(): v for k, v in env.items()}
        else:
            env_lookup = env

        def _normalise(key: str) -> str:
            return key if case_sensitive else key.lower()

        values: dict[str, Any] = {}

        for name, field_info in cls.__rivex_fields__.items():  # type: ignore[attr-defined]
            # Field-level alias (set via Field(alias=...)) wins as the env
            # key; otherwise fall back to ``<prefix><FIELD_NAME>``.
            env_key = field_info.alias or f"{prefix}{name}"
            looked = _normalise(env_key)
            if looked in env_lookup:
                values[name] = env_lookup[looked]
                continue

            # Nested Schema field? Collect children under the delimiter.
            field_type = cls.__annotations__.get(name)
            if isinstance(field_type, type) and issubclass(field_type, Schema):
                nested_prefix = _normalise(env_key) + _normalise(nested_delim)
                child: dict[str, str] = {}
                for k, v in env_lookup.items():
                    if k.startswith(nested_prefix):
                        child[k[len(nested_prefix) :]] = v
                if child:
                    values[name] = child

        return values

    @classmethod
    def from_env(cls) -> Any:
        """Build a Settings instance from ``os.environ`` + optional ``.env``.

        The return type is ``Any`` rather than ``Self`` so subclasses
        get the right inferred type back without ``cast()`` boilerplate
        — pydantic_core actually returns an instance of ``cls``.
        """
        env = cls._build_env()
        values = cls._collect_values(env)
        return cls.model_validate(values)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Any:
        """Build a Settings instance from an arbitrary mapping.

        Convenience for tests — bypasses env reading entirely.
        """
        return cls.model_validate(data)
