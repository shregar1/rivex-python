from __future__ import annotations

import asyncio
import json
from collections.abc import Callable


class HeartbeatManager:
    def __init__(
        self,
        ping_interval: float = 25.0,
        pong_timeout: float = 10.0,
        on_timeout: Callable | None = None,
    ):
        self._ping_interval = ping_interval
        self._pong_timeout = pong_timeout
        self._on_timeout = on_timeout
        self._tasks: dict[int, asyncio.Task] = {}
        self._pending_pong: dict[int, bool] = {}

    async def start(self, connection_id: int, send: Callable, close: Callable) -> None:
        if connection_id in self._tasks:
            return

        async def _beat():
            try:
                while True:
                    await asyncio.sleep(self._ping_interval)
                    self._pending_pong[connection_id] = True
                    try:
                        await send(json.dumps({"type": "ping"}))
                    except Exception:
                        break
                    await asyncio.sleep(self._pong_timeout)
                    if self._pending_pong.pop(connection_id, False):
                        if self._on_timeout:
                            await self._on_timeout(connection_id)
                        try:
                            await close(4000, "heartbeat timeout")
                        except Exception:
                            pass
                        break
            except asyncio.CancelledError:
                pass
            finally:
                self._pending_pong.pop(connection_id, None)
                self._tasks.pop(connection_id, None)

        self._tasks[connection_id] = asyncio.create_task(_beat())

    async def pong_received(self, connection_id: int) -> None:
        self._pending_pong[connection_id] = False

    async def stop(self, connection_id: int) -> None:
        task = self._tasks.pop(connection_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._pending_pong.pop(connection_id, None)

    async def stop_all(self) -> None:
        for cid in list(self._tasks):
            await self.stop(cid)
