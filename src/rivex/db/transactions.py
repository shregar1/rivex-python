from __future__ import annotations

import contextvars
from types import TracebackType
from typing import Any

_transaction_stack: contextvars.ContextVar[list[Any]] = contextvars.ContextVar(
    "rivex_transaction_stack", default=[]
)


class Transaction:
    """Represents a database transaction with savepoint support.

    Usage::

        async with app.db.transaction():
            await app.db.execute("INSERT INTO ...")
            # automatic rollback on exception
    """

    def __init__(self, pool, savepoint: bool = True):
        self._pool = pool
        self._savepoint = savepoint
        self._conn = None
        self._savepoint_name: str | None = None
        self._active = False

    async def __aenter__(self) -> Transaction:
        self._conn = await self._pool.acquire()
        if self._savepoint:
            stack = _transaction_stack.get()
            if stack:
                # Inside existing transaction, create savepoint
                sp_id = len(stack)
                self._savepoint_name = f"sp_{sp_id}"
                await self._conn.execute(f"SAVEPOINT {self._savepoint_name}")
                stack.append(self)
            else:
                await self._conn.execute("BEGIN")
                stack.append(self)
        else:
            await self._conn.execute("BEGIN")
            _transaction_stack.get().append(self)
        self._active = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        stack = _transaction_stack.get()
        if not self._active:
            if self._conn:
                await self._pool.release(self._conn)
            return False

        try:
            if exc_type is not None:
                await self._rollback_internal()
                return False
            else:
                await self._commit_internal()
                return True
        finally:
            if stack and stack[-1] is self:
                stack.pop()
            self._active = False
            if self._conn:
                await self._pool.release(self._conn)
                self._conn = None

    async def _commit_internal(self) -> None:
        if self._savepoint_name:
            await self._conn.execute(f"RELEASE SAVEPOINT {self._savepoint_name}")
        else:
            await self._conn.execute("COMMIT")

    async def _rollback_internal(self) -> None:
        if self._savepoint_name:
            await self._conn.execute(f"ROLLBACK TO SAVEPOINT {self._savepoint_name}")
        else:
            await self._conn.execute("ROLLBACK")

    async def commit(self) -> None:
        await self._commit_internal()
        self._active = False

    async def rollback(self) -> None:
        await self._rollback_internal()
        self._active = False

    async def savepoint(self) -> str:
        sp_id = id(self)
        name = f"savepoint_{sp_id}"
        await self._conn.execute(f"SAVEPOINT {name}")
        return name

    async def rollback_to_savepoint(self, name: str) -> None:
        await self._conn.execute(f"ROLLBACK TO SAVEPOINT {name}")

    async def release_savepoint(self, name: str) -> None:
        await self._conn.execute(f"RELEASE SAVEPOINT {name}")


class atomic:
    """Decorator or context manager for database transactions.

    As a decorator::

        @atomic()
        async def my_view(request):
            ...

    As a context manager::

        async with atomic():
            ...
    """

    def __init__(self, pool=None, savepoint: bool = True):
        self._pool = pool
        self._savepoint = savepoint

    async def __aenter__(self) -> Transaction:
        pool = self._pool
        if pool is None:
            from rivex.applications import Rivex
            app = Rivex.get_current()
            pool = app.db
        self._transaction = Transaction(pool, savepoint=self._savepoint)
        return await self._transaction.__aenter__()

    async def __aexit__(self, *args: Any) -> bool:
        return await self._transaction.__aexit__(*args)

    def __call__(self, func):
        from functools import wraps

        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with self:
                return await func(*args, **kwargs)
        return wrapper
