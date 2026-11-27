from __future__ import annotations

import abc
import json
from typing import Any


class MultiServerBackend(abc.ABC):
    @abc.abstractmethod
    async def publish(self, channel: str, message: Any) -> None:
        """Publish ``message`` to ``channel`` for fanout across the cluster.

        Args:
            channel: Logical channel / subject to publish on.
            message: Any JSON-serialisable Python value; some backends
                accept pre-serialised strings or bytes too.
        """
        ...

    @abc.abstractmethod
    async def subscribe(self, channel: str, callback: Any) -> None:
        """Register ``callback`` to be invoked for every message on ``channel``.

        Args:
            channel: Logical channel / subject to listen on.
            callback: Awaitable invoked with each decoded message payload
                received from the backend.
        """
        ...

    @abc.abstractmethod
    async def unsubscribe(self, channel: str) -> None:
        """Stop receiving messages on ``channel``.

        Args:
            channel: Logical channel / subject to stop listening on.
        """
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Tear down the backend and release all of its resources.

        After this call the backend instance is no longer usable.
        """
        ...


class RedisPubSubBackend(MultiServerBackend):
    def __init__(self, url: str = "redis://localhost:6379"):
        self._url = url
        self._redis = None
        self._pubsub = None
        self._callbacks: dict[str, Any] = {}
        self._listener_task = None

    async def publish(self, channel: str, message: Any) -> None:
        """Publish ``message`` on ``channel`` via a short-lived Redis client.

        Opens a fresh Redis connection for each call so the backend is
        safe to share between coroutines. Strings and bytes are forwarded
        verbatim; anything else is JSON-encoded first. The client is
        always closed, even on failure.

        Args:
            channel: Redis channel name to publish on.
            message: Payload to publish; either a string/bytes or a
                JSON-serialisable Python value.
        """
        import redis.asyncio as aioredis

        r = await aioredis.from_url(self._url)
        try:
            payload = json.dumps(message) if not isinstance(message, (str, bytes)) else message
            await r.publish(channel, payload)
        finally:
            await r.close()

    async def subscribe(self, channel: str, callback: Any) -> None:
        """Register ``callback`` for messages arriving on ``channel``.

        Lazily creates the shared Redis client and pubsub object the first
        time a subscription is requested, then starts the background
        listener task if it is not already running. Re-subscribing to the
        same channel simply replaces the registered callback.

        Args:
            channel: Redis channel name to listen on.
            callback: Awaitable invoked with each decoded message payload.
        """
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
        """Stop receiving messages on ``channel`` and drop its callback.

        Args:
            channel: Redis channel name to unsubscribe from. Unknown
                channels are ignored.
        """
        if self._pubsub:
            await self._pubsub.unsubscribe(channel)
        self._callbacks.pop(channel, None)

    async def _listener(self) -> None:
        """Background task that pumps messages from Redis to callbacks.

        Decodes the channel and payload, attempts a JSON parse (falling
        back to the raw bytes on failure), and invokes the registered
        callback. Errors raised by individual callbacks are swallowed so
        one bad subscriber cannot disrupt the others.
        """
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
        """Stop the listener task and close the Redis connections.

        Safe to call multiple times; missing components are silently
        skipped.
        """
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
        """Publish ``message`` on ``channel`` via a short-lived NATS client.

        Opens a fresh NATS connection per call so the backend is safe to
        share between coroutines. Strings and bytes are forwarded
        verbatim; anything else is JSON-encoded. The client is always
        closed, even on failure.

        Args:
            channel: NATS subject to publish on.
            message: Payload to publish; either a string/bytes or a
                JSON-serialisable Python value.
        """
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
        """Register ``callback`` for messages arriving on ``channel``.

        Lazily opens the shared NATS connection the first time it is
        needed and registers an internal handler that decodes the payload
        before forwarding it to ``callback``. The most recent
        subscription is retained on ``self._sub`` so
        :meth:`unsubscribe` can find it.

        Args:
            channel: NATS subject to listen on.
            callback: Awaitable invoked with each decoded message payload.
        """
        import nats

        if self._nc is None:
            self._nc = await nats.connect(self._url)

        async def _handler(msg):
            """Decode one inbound NATS message and forward it.

            Attempts a JSON parse on the decoded bytes; on failure the
            raw bytes are passed through so the subscriber still gets
            something useful.
            """
            try:
                data = json.loads(msg.data.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = msg.data
            await callback(data)

        sub = await self._nc.subscribe(channel, cb=_handler)
        self._sub = sub

    async def unsubscribe(self, channel: str) -> None:
        """Cancel the most recent subscription.

        Only the last subscription is tracked, so calling this when the
        current subscription is for a different ``channel`` will still
        cancel it. Idempotent if no subscription exists.
        """
        if hasattr(self, "_sub"):
            await self._sub.unsubscribe()
            del self._sub

    async def close(self) -> None:
        """Close the shared NATS connection if one is open."""
        if self._nc:
            await self._nc.close()
            self._nc = None
