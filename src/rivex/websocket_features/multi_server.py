from __future__ import annotations

import abc
import json
from typing import Any


class MultiServerBackend(abc.ABC):
    @abc.abstractmethod
    async def publish(self, channel: str, message: Any) -> None: ...

    @abc.abstractmethod
    async def subscribe(self, channel: str, callback: Any) -> None: ...

    @abc.abstractmethod
    async def unsubscribe(self, channel: str) -> None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...


class RedisPubSubBackend(MultiServerBackend):
    def __init__(self, url: str = "redis://localhost:6379"):
        self._url = url
        self._redis = None
        self._pubsub = None
        self._callbacks: dict[str, Any] = {}
        self._listener_task = None

    async def publish(self, channel: str, message: Any) -> None:
        import redis.asyncio as aioredis

        r = await aioredis.from_url(self._url)
        try:
            payload = json.dumps(message) if not isinstance(message, (str, bytes)) else message
            await r.publish(channel, payload)
        finally:
            await r.close()

    async def subscribe(self, channel: str, callback: Any) -> None:
        import redis.asyncio as aioredis

        self._callbacks[channel] = callback
        if self._redis is None:
            self._redis = await aioredis.from_url(self._url)
            self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(channel)
        if self._listener_task is None:
            import asyncio

            self._listener_task = asyncio.create_task(self._listener())

    async def unsubscribe(self, channel: str) -> None:
        if self._pubsub:
            await self._pubsub.unsubscribe(channel)
        self._callbacks.pop(channel, None)

    async def _listener(self) -> None:
        if not self._pubsub:
            return
        async for msg in self._pubsub.listen():
            if msg["type"] != "message":
                continue
            channel = (
                msg["channel"].decode() if isinstance(msg["channel"], bytes) else msg["channel"]
            )
            cb = self._callbacks.get(channel)
            if cb:
                try:
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    try:
                        data = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        pass
                    await cb(data)
                except Exception:
                    pass

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except Exception:
                pass
            self._listener_task = None
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
            self._redis = None


class NATSBackend(MultiServerBackend):
    def __init__(self, url: str = "nats://localhost:4222"):
        self._url = url
        self._nc = None

    async def publish(self, channel: str, message: Any) -> None:
        import nats

        nc = await nats.connect(self._url)
        try:
            payload = json.dumps(message) if not isinstance(message, (str, bytes)) else message
            if isinstance(payload, str):
                payload = payload.encode()
            await nc.publish(channel, payload)
        finally:
            await nc.close()

    async def subscribe(self, channel: str, callback: Any) -> None:
        import nats

        if self._nc is None:
            self._nc = await nats.connect(self._url)

        async def _handler(msg):
            try:
                data = json.loads(msg.data.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = msg.data
            await callback(data)

        sub = await self._nc.subscribe(channel, cb=_handler)
        self._sub = sub

    async def unsubscribe(self, channel: str) -> None:
        if hasattr(self, "_sub"):
            await self._sub.unsubscribe()
            del self._sub

    async def close(self) -> None:
        if self._nc:
            await self._nc.close()
            self._nc = None
