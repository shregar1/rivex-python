from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("rivex.mqtt")


class MQTTBridge:
    """MQTT over WebSocket bridge for IoT messaging.

    Connects to an MQTT broker and exposes topics via WebSocket,
    allowing browser clients to publish/subscribe to MQTT messages.

    Usage::

        bridge = MQTTBridge(broker="localhost", port=1883)

        @bridge.on_message("sensors/temperature")
        async def on_temp(client, topic, payload):
            print(f"Temperature: {payload}")

        await bridge.connect()

        # In WebSocket handler:
        await bridge.handle_websocket(websocket, subscriptions=["sensors/#"])
    """

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        client_id: str = "rivex-mqtt-bridge",
        use_tls: bool = False,
    ):
        self._broker = broker
        self._port = port
        self._username = username
        self._password = password
        self._client_id = client_id
        self._use_tls = use_tls
        self._client = None
        self._message_handlers: dict[str, list[Callable]] = {}
        self._ws_clients: dict[str, Callable] = {}
        self._ws_subscriptions: dict[str, list[str]] = {}
        self._connected = False

    async def connect(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt required. Install with: pip install paho-mqtt")
            return

        self._client = mqtt.Client(client_id=self._client_id, protocol=mqtt.MQTTv311)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        if self._username and self._password:
            self._client.username_pw_set(self._username, self._password)

        if self._use_tls:
            self._client.tls_set()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._client.connect, self._broker, self._port, 60)
        self._client.loop_start()
        self._connected = True
        logger.info(f"Connected to MQTT broker at {self._broker}:{self._port}")

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            logger.info("MQTT connected successfully")
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def _on_message(self, client, userdata, msg) -> None:
        topic = msg.topic
        payload = msg.payload.decode() if isinstance(msg.payload, bytes) else str(msg.payload)

        for pattern, handlers in self._message_handlers.items():
            if self._topic_matches(pattern, topic):
                for handler in handlers:
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.ensure_future(handler(topic, payload))
                        else:
                            loop.run_until_complete(handler(topic, payload))
                    except Exception as e:
                        logger.error(f"MQTT handler error: {e}")

        self._forward_to_ws_clients(topic, payload)

    def _topic_matches(self, pattern: str, topic: str) -> bool:
        pattern_parts = pattern.split("/")
        topic_parts = topic.split("/")
        if len(pattern_parts) > len(topic_parts) and pattern_parts[-1] != "#":
            return False
        for i, p in enumerate(pattern_parts):
            if p == "#":
                return True
            if p == "+":
                continue
            if i >= len(topic_parts) or p != topic_parts[i]:
                return False
        return len(pattern_parts) == len(topic_parts)

    def _forward_to_ws_clients(self, topic: str, payload: str) -> None:
        message = json.dumps({"topic": topic, "payload": payload})
        for ws_id, send_func in list(self._ws_clients.items()):
            subs = self._ws_subscriptions.get(ws_id, [])
            if any(self._topic_matches(s, topic) for s in subs):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(send_func(message))
                except Exception:
                    self._ws_clients.pop(ws_id, None)

    def on_message(self, topic: str):
        """Decorator to register a handler for MQTT messages on a topic.

        Supports MQTT wildcards: ``+`` (single level), ``#`` (multi level).
        """
        def decorator(func: Callable) -> Callable:
            self._message_handlers.setdefault(topic, []).append(func)
            return func
        return decorator

    async def publish(self, topic: str, payload: Any, qos: int = 0) -> None:
        if not self._client or not self._connected:
            raise ConnectionError("MQTT client not connected")
        if not isinstance(payload, (str, bytes)):
            payload = json.dumps(payload)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._client.publish, topic, payload, qos)

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        if not self._client:
            raise ConnectionError("MQTT client not connected")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._client.subscribe, topic, qos)

    def register_ws_client(self, ws_id: str, send_func: Callable, subscriptions: list[str] | None = None) -> None:
        self._ws_clients[ws_id] = send_func
        self._ws_subscriptions[ws_id] = subscriptions or ["#"]

    def unregister_ws_client(self, ws_id: str) -> None:
        self._ws_clients.pop(ws_id, None)
        self._ws_subscriptions.pop(ws_id, None)

    async def handle_websocket(self, websocket, subscriptions: list[str] | None = None) -> None:
        ws_id = str(id(websocket))
        self.register_ws_client(ws_id, websocket.send, subscriptions)
        try:
            while True:
                msg = await websocket.receive()
                try:
                    data = json.loads(msg)
                    topic = data.get("topic", "")
                    payload = data.get("payload", "")
                    if topic:
                        await self.publish(topic, payload)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        finally:
            self.unregister_ws_client(ws_id)

    async def disconnect(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
            logger.info("Disconnected from MQTT broker")
