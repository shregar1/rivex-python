"""``rivex.dtos.headers`` — HTTP Headers DTO model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

from rivex.dtos.abstraction import IDTO
from rivex.serialization.serialization import serialize


@dataclass
class HeaderDTO(IDTO, Mapping[str, str]):
    """Encapsulated model for HTTP headers dict representation.

    Provides case-insensitive lookup, conversion to dict/tuples, and
    direct integration with response DTOs.
    """

    entries: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized: dict[str, str] = {}
        for k, v in self.entries.items():
            normalized[k.lower()] = str(v)
        self.entries = normalized

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the header value for ``key`` (case-insensitive), or ``default``.

        Args:
            key: Header name. Compared lowercased against stored keys.
            default: Value returned when ``key`` is not present.

        Returns:
            The stored string value, or ``default`` if ``key`` is
            unknown.
        """
        return self.entries.get(key.lower(), default)

    def set(self, key: str, value: str) -> None:
        """Insert or replace the header ``key`` with ``value`` (case-insensitive).

        ``value`` is coerced to ``str`` before storage so callers may
        pass non-string values without surprises.

        Args:
            key: Header name. Stored lowercased.
            value: Header value; converted to ``str`` before storage.
        """
        self.entries[key.lower()] = str(value)

    def delete(self, key: str) -> None:
        """Remove the header ``key`` (case-insensitive) if it exists.

        No error is raised when ``key`` is absent.

        Args:
            key: Header name. Compared lowercased against stored keys.
        """
        self.entries.pop(key.lower(), None)

    def to_dict(self) -> dict[str, str]:
        """Return a shallow copy of the headers as a regular dict.

        Returns:
            A new ``dict`` mapping lowercased header names to their
            string values. Mutations to the returned dict do not
            affect this DTO.
        """
        return dict(self.entries)

    def to_tuples(self) -> list[tuple[str, str]]:
        """Return the headers as a list of ``(name, value)`` pairs.

        Returns:
            A new list of ``(name, value)`` tuples suitable for the
            ``headers`` field of a response DTO.
        """
        return list(self.entries.items())

    def to_json(self) -> bytes:
        """Serialize the headers to a JSON byte string.

        Returns:
            The JSON encoding of :meth:`to_dict` via the configured
            :func:`serialize` helper.
        """
        return serialize(self.to_dict())

    def __getitem__(self, key: str) -> str:
        return self.entries[key.lower()]

    def __iter__(self) -> Iterator[str]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    @classmethod
    def from_dict(cls, data: dict[str, str] | None = None) -> HeaderDTO:
        """Build a :class:`HeaderDTO` from a regular mapping.

        Args:
            data: Mapping of header names to values. ``None`` is
                treated as an empty mapping. Keys are normalized to
                lower case by :meth:`__post_init__`.

        Returns:
            A new :class:`HeaderDTO` populated from ``data``.
        """
        return cls(entries=data or {})

    @classmethod
    def from_tuples(cls, items: list[tuple[str, str]]) -> HeaderDTO:
        """Build a :class:`HeaderDTO` from an iterable of ``(name, value)`` pairs.

        Args:
            items: Iterable of header pairs to store. Keys are
                normalized to lower case by :meth:`__post_init__`.

        Returns:
            A new :class:`HeaderDTO` populated from ``items``.
        """
        return cls(entries={k: v for k, v in items})


__all__ = ["HeaderDTO"]
