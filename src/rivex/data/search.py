from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SearchBackend(ABC):
    """Abstract search backend interface."""

    @abstractmethod
    async def index(self, model: str, obj_id: Any, body: dict) -> dict:
        ...

    @abstractmethod
    async def remove(self, model: str, obj_id: Any) -> dict:
        ...

    @abstractmethod
    async def search(self, query: str, models: list[str] | None = None,
                     limit: int = 20, offset: int = 0) -> dict:
        ...

    @abstractmethod
    async def reindex(self, model: str, items: list[tuple[Any, dict]]) -> dict:
        ...

    @abstractmethod
    async def delete_index(self, model: str) -> dict:
        ...


class PostgresSearchBackend(SearchBackend):
    """PostgreSQL full-text search via ``tsvector`` / ``tsquery``.

    Usage::

        backend = PostgresSearchBackend(pool)
        await backend.search("python", models=["article"])
    """

    def __init__(self, pool):
        self._pool = pool

    def _tsquery(self, query: str) -> str:
        terms = " | ".join(query.strip().split())
        return f"to_tsquery('english', '{terms}')"

    def _tsvector(self, columns: list[str]) -> str:
        return " || ".join(f"coalesce(to_tsvector('english', {c}), ''::tsvector)" for c in columns)

    async def index(self, model: str, obj_id: Any, body: dict) -> dict:
        table = model.lower()
        columns = list(body.keys())
        tsvector = self._tsvector(columns)
        values = ", ".join(f"${i+1}" for i in range(len(columns)))
        set_clause = ", ".join(f"{c} = ${i+1}" for i, c in enumerate(columns))
        search_col = f"{table}_search"
        await self._pool.execute(
            f"INSERT INTO {table} (id, {', '.join(columns)}, {search_col}) "
            f"VALUES ($1, {values}, {tsvector}) "
            f"ON CONFLICT (id) DO UPDATE SET {set_clause}",
            obj_id, *body.values()
        )
        return {"indexed": True, "model": model, "id": obj_id}

    async def remove(self, model: str, obj_id: Any) -> dict:
        table = model.lower()
        await self._pool.execute(f"DELETE FROM {table} WHERE id = $1", obj_id)
        return {"removed": True, "model": model, "id": obj_id}

    async def search(self, query: str, models: list[str] | None = None,
                     limit: int = 20, offset: int = 0) -> dict:
        results: list[dict] = []
        total = 0
        for model in models or []:
            table = model.lower()
            tsquery = self._tsquery(query)
            rows = await self._pool.fetch(
                f"SELECT *, ts_rank_cd({table}_search, {tsquery}) AS rank "
                f"FROM {table} "
                f"WHERE {table}_search @@ {tsquery} "
                f"ORDER BY rank DESC LIMIT $1 OFFSET $2",
                limit, offset
            )
            for row in rows:
                results.append(dict(row))
            total += len(rows)
        return {"results": results, "total": total, "query": query}

    async def reindex(self, model: str, items: list[tuple[Any, dict]]) -> dict:
        for obj_id, body in items:
            await self.index(model, obj_id, body)
        return {"reindexed": True, "model": model, "count": len(items)}

    async def delete_index(self, model: str) -> dict:
        table = model.lower()
        try:
            await self._pool.execute(f"UPDATE {table} SET {table}_search = NULL")
        except Exception:
            pass
        return {"deleted": True, "model": model}


class ElasticsearchBackend(SearchBackend):
    """Elasticsearch search backend.

    Usage::

        backend = ElasticsearchBackend(url="http://localhost:9200")
        await backend.search("python")
    """

    def __init__(self, url: str = "http://localhost:9200", **client_kwargs):
        try:
            from elasticsearch import AsyncElasticsearch
        except ImportError:
            raise ImportError("elasticsearch library required for ElasticsearchBackend")
        self._client = AsyncElasticsearch(url, **client_kwargs)
        self._url = url

    async def index(self, model: str, obj_id: Any, body: dict) -> dict:
        result = await self._client.index(index=model.lower(), id=obj_id, document=body)
        return {"indexed": True, "model": model, "id": obj_id, "result": result["result"]}

    async def remove(self, model: str, obj_id: Any) -> dict:
        try:
            result = await self._client.delete(index=model.lower(), id=obj_id)
            return {"removed": True, "model": model, "id": obj_id}
        except Exception as e:
            return {"removed": False, "model": model, "id": obj_id, "error": str(e)}

    async def search(self, query: str, models: list[str] | None = None,
                     limit: int = 20, offset: int = 0) -> dict:
        indices = ",".join(m.lower() for m in models) if models else "_all"
        result = await self._client.search(
            index=indices,
            query={"multi_match": {"query": query, "fields": ["*"]}},
            size=limit,
            from_=offset,
        )
        hits = result["hits"]["hits"]
        return {
            "results": [{"_id": h["_id"], "_index": h["_index"], **h["_source"]} for h in hits],
            "total": result["hits"]["total"]["value"],
            "query": query,
        }

    async def reindex(self, model: str, items: list[tuple[Any, dict]]) -> dict:
        for obj_id, body in items:
            await self.index(model, obj_id, body)
        return {"reindexed": True, "model": model, "count": len(items)}

    async def delete_index(self, model: str) -> dict:
        try:
            await self._client.indices.delete(index=model.lower())
            return {"deleted": True, "model": model}
        except Exception as e:
            return {"deleted": False, "model": model, "error": str(e)}
