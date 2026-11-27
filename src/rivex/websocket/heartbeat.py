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
        """Begin sending periodic pings to ``connection_id``.

        Spawns a background task that pings the connection every
        ``ping_interval`` seconds, waits up to ``pong_timeout`` for a
        matching :meth:`pong_received`, and invokes the configured
        ``on_timeout`` callback plus ``close`` when a ping goes unanswered.
        No-op when a heartbeat is already running for the connection.

        Args:
            connection_id: Numeric id of the WebSocket connection to
                monitor.
            send: Awaitable callable used to deliver the encoded ping
                frame. Errors are treated as a closed connection and stop
                the heartbeat.
            close: Awaitable callable invoked with ``(code, reason)`` when
                the connection fails to respond. Errors are swallowed.
        """
        if connection_id in self._tasks:
            return

        async def _beat():
            """Single-connection ping loop spawned by :meth:`start`."""
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
        """Mark an outstanding ping as answered for ``connection_id``.

        Clears the pending flag so the heartbeat loop's next timeout check
        does not fire ``on_timeout`` and close the connection.

        Args:
            connection_id: Numeric id of the WebSocket connection that just
                replied with a pong.
        """
        self._pending_pong[connection_id] = False

    async def stop(self, connection_id: int) -> None:
        """Cancel the heartbeat task for ``connection_id`` if it is running.

        Looks up the background task, cancels it, and awaits it so the
        ``finally`` block inside :meth:`start`'s inner loop runs to
        completion. The pending-pong entry is cleared as well.

        Args:
            connection_id: Numeric id of the WebSocket connection whose
                heartbeat should be torn down.
        """
        task = self._tasks.pop(connection_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._pending_pong.pop(connection_id, None)

    async def stop_all(self) -> None:
        """Cancel the heartbeat for every tracked connection.

        Iterates over a snapshot of the task map so :meth:`stop` can mutate
        the underlying dict as each connection is torn down. Typically
        called during server shutdown to halt all background heartbeats.
        """
        for cid in list(self._tasks):
            await self.stop(cid)
