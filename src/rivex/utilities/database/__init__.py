"""``rivex.utilities.database`` — connection-management helpers for MongoDB and Postgres.

The driver libraries (``motor``, ``asyncpg``) are imported lazily inside
each utility's ``connect()`` method so installing Rivex doesn't force
either driver on consumers. A missing driver degrades the utility to
"disconnected" mode rather than failing at import time.
"""

from __future__ import annotations

from rivex.utilities.database.abstraction import IDatabaseUtility
from rivex.utilities.database.mongo import MongoDatabaseUtility
from rivex.utilities.database.postgres import PostgresDatabaseUtility

__all__ = [
    "IDatabaseUtility",
    "MongoDatabaseUtility",
    "PostgresDatabaseUtility",
]
