"""``rivex.constants.db`` — generic database column / table naming helpers.

These are the columns that every Rivex-managed table is expected to
have (audit + URN). For domain-specific columns and physical table
names, keep using your app-local ``constants.db.DBColumn`` /
``constants.db.DBTable`` modules.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.abstraction import IConstant


class AuditColumn(IConstant):
    """Common columns present on every Rivex-managed table."""

    ID: Final[str] = "id"
    URN: Final[str] = "urn"
    CREATED_AT: Final[str] = "created_at"
    UPDATED_AT: Final[str] = "updated_at"
    CREATED_BY: Final[str] = "created_by"
    UPDATED_BY: Final[str] = "updated_by"
    IS_DELETED: Final[str] = "is_deleted"
    IS_ACTIVE: Final[str] = "is_active"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "AuditColumn"


__all__ = ["AuditColumn"]
