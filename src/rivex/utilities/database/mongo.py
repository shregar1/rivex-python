"""MongoDB utility — connection management and document-store helpers.

The ``motor`` package is imported lazily inside :meth:`connect`. When
it isn't installed the utility stays in a disconnected state and every
collection lookup returns ``None`` so the rest of the app can boot.
"""

from __future__ import annotations

from typing import Any, Optional

from rivex.utilities.abstraction import LayeredUtility
from rivex.utilities.database.abstraction import IDatabaseUtility


class MongoDatabaseUtility(IDatabaseUtility, LayeredUtility):
    """Thin wrapper around a motor / pymongo client with safe lifecycle helpers."""

    def __init__(
        self,
        connection_uri: str,
        database: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.connection_uri = connection_uri
        self.database = database
        self._client: Any = None

    async def connect(self) -> Any:
        """Open a MongoDB client and return it (``motor.AsyncIOMotorClient``)."""
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            self._client = AsyncIOMotorClient(self.connection_uri)
            return self._client
        except ImportError:
            self._client = None
            return None

    async def disconnect(self) -> None:
        """Close the underlying MongoDB client."""
        if self._client is not None and hasattr(self._client, "close"):
            self._client.close()
        self._client = None

    def get_collection(self, name: str) -> Any:
        """Return a collection handle from the active client (``None`` when disconnected)."""
        if self._client is None:
            return None
        return self._client[self.database][name]

    @property
    def client(self) -> Any:
        return self._client

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "MongoDatabaseUtility"


__all__ = ["MongoDatabaseUtility"]
