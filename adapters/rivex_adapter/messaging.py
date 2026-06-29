"""
Messaging / queue adapters for AWS SQS, Azure Queue, Azure Service Bus,
GCP Pub/Sub, and Apache Kafka.

All adapters follow the same minimal async interface::

    async with QueueAdapter(url="...") as q:
        await q.send({"key": "value"})
        message = await q.receive()
        await q.delete(message)

Each adapter is auto-registered by ``import rivex_adapter``.
"""

from __future__ import annotations

import json
from typing import Any


class QueueAdapter:
    """Base class for queue adapters."""

    def __init__(self, url: str, **kwargs: Any):
        self.url = url
        self._kwargs = kwargs
        self._client: Any = None

    async def __aenter__(self) -> QueueAdapter:
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Open the connection / create the client."""

    async def disconnect(self) -> None:
        """Close the connection."""

    async def send(self, message: Any, **kwargs: Any) -> str | None:
        """Send a message. Returns a message ID if available."""
        raise NotImplementedError

    async def receive(self, **kwargs: Any) -> Any | None:
        """Receive a single message."""
        raise NotImplementedError

    async def delete(self, message: Any) -> None:
        """Acknowledge / delete a received message."""


class SqsAdapter(QueueAdapter):
    """AWS SQS adapter."""

    async def connect(self) -> None:
        import aioboto3

        self._session = aioboto3.Session()
        parts = self.url.replace("sqs://", "").split("/", 1)
        region = parts[0] if "." in parts[0] else "us-east-1"
        queue_url = parts[1] if len(parts) > 1 else parts[0]
        self._client = await self._session.client("sqs", region_name=region).__aenter__()
        self._queue_url = f"https://sqs.{region}.amazonaws.com/{queue_url}"

    async def disconnect(self) -> None:
        if self._client:
            await self._client.__aexit__(None, None, None)

    async def send(self, message: Any, **kwargs: Any) -> str | None:
        body = json.dumps(message) if not isinstance(message, str) else message
        resp = await self._client.send_message(
            QueueUrl=self._queue_url, MessageBody=body, **kwargs
        )
        return resp.get("MessageId")

    async def receive(self, **kwargs: Any) -> dict | None:
        resp = await self._client.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=kwargs.get("wait_time", 5),
        )
        msgs = resp.get("Messages", [])
        if not msgs:
            return None
        msg = msgs[0]
        return {
            "id": msg["MessageId"],
            "body": json.loads(msg["Body"]) if msg["Body"].startswith(("{", "[")) else msg["Body"],
            "receipt_handle": msg["ReceiptHandle"],
            "_raw": msg,
        }

    async def delete(self, message: Any) -> None:
        receipt = message["receipt_handle"] if isinstance(message, dict) else message
        await self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt)


class AzureQueueAdapter(QueueAdapter):
    """Azure Queue Storage adapter."""

    async def connect(self) -> None:
        from azure.storage.queue import QueueServiceClient, QueueClient

        self._service = QueueServiceClient.from_connection_string(
            self._kwargs.get("connection_string", "")
        )
        queue_name = self.url.replace("azurequeue://", "")
        self._client = self._service.get_queue_client(queue_name)

    async def disconnect(self) -> None:
        self._client = None
        self._service = None

    async def send(self, message: Any, **kwargs: Any) -> str | None:
        import base64

        body = json.dumps(message) if not isinstance(message, str) else message
        self._client.send_message(base64.b64encode(body.encode()).decode())
        return None

    async def receive(self, **kwargs: Any) -> dict | None:
        import base64

        msgs = self._client.receive_messages(max_messages=1, **kwargs)
        for msg in msgs:
            decoded = base64.b64decode(msg.content).decode()
            return {
                "id": msg.id,
                "body": json.loads(decoded) if decoded.startswith(("{", "[")) else decoded,
                "pop_receipt": msg.pop_receipt,
                "_raw": msg,
            }
        return None

    async def delete(self, message: Any) -> None:
        self._client.delete_message(message["id"], message["pop_receipt"])


class ServiceBusAdapter(QueueAdapter):
    """Azure Service Bus adapter."""

    async def connect(self) -> None:
        from azure.servicebus.aio import ServiceBusClient

        conn_str = self._kwargs.get("connection_string", "")
        self._sb_client = ServiceBusClient.from_connection_string(conn_str)
        queue_or_topic = self.url.replace("servicebus://", "")
        self._receiver = self._sb_client.get_queue_receiver(queue_or_topic)
        self._sender = self._sb_client.get_queue_sender(queue_or_topic)

    async def disconnect(self) -> None:
        await self._receiver.close()
        await self._sender.close()
        await self._sb_client.close()

    async def send(self, message: Any, **kwargs: Any) -> str | None:
        from azure.servicebus import ServiceBusMessage

        body = json.dumps(message) if not isinstance(message, str) else message
        sb_msg = ServiceBusMessage(body)
        await self._sender.send_messages(sb_msg)
        return str(sb_msg.message_id)

    async def receive(self, **kwargs: Any) -> dict | None:
        msgs = await self._receiver.receive_messages(max_message_count=1, **kwargs)
        if not msgs:
            return None
        msg = msgs[0]
        body = msg.body_as_str() if hasattr(msg, "body_as_str") else str(msg.body)
        return {
            "id": str(msg.message_id),
            "body": json.loads(body) if body.startswith(("{", "[")) else body,
            "_raw": msg,
        }

    async def delete(self, message: Any) -> None:
        raw = message["_raw"] if isinstance(message, dict) else message
        await self._receiver.complete_message(raw)


class GcpPubSubAdapter(QueueAdapter):
    """GCP Pub/Sub adapter."""

    async def connect(self) -> None:
        from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient

        self._publisher = PublisherClient()
        self._subscriber = SubscriberClient()
        parts = self.url.replace("pubsub://", "").split("/", 1)
        self._project = parts[0]
        self._topic_or_sub = parts[1] if len(parts) > 1 else "default"
        self._topic_path = self._publisher.topic_path(self._project, self._topic_or_sub)
        self._subscription_path = self._subscriber.subscription_path(
            self._project, self._topic_or_sub
        )

    async def disconnect(self) -> None:
        await self._publisher.close()
        await self._subscriber.close()

    async def send(self, message: Any, **kwargs: Any) -> str | None:
        from google.cloud.pubsub_v1.types import PubsubMessage

        body = json.dumps(message).encode() if not isinstance(message, bytes) else message
        pb_msg = PubsubMessage(data=body)
        future = self._publisher.publish(self._topic_path, pb_msg.data)
        return future.result()

    async def receive(self, **kwargs: Any) -> dict | None:
        from google.cloud.pubsub_v1 import subscriber

        resp = await self._subscriber.pull(
            request={"subscription": self._subscription_path, "max_messages": 1}
        )
        if not resp.received_messages:
            return None
        msg = resp.received_messages[0]
        body = msg.message.data.decode()
        return {
            "id": msg.message.message_id,
            "body": json.loads(body) if body.startswith(("{", "[")) else body,
            "ack_id": msg.ack_id,
            "_raw": msg,
        }

    async def delete(self, message: Any) -> None:
        ack_id = message["ack_id"] if isinstance(message, dict) else message
        await self._subscriber.acknowledge(
            request={"subscription": self._subscription_path, "ack_ids": [ack_id]}
        )


class KafkaAdapter(QueueAdapter):
    """Apache Kafka adapter via ``aiokafka``."""

    async def connect(self) -> None:
        from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

        parts = self.url.replace("kafka://", "").split("/", 1)
        bootstrap = parts[0]
        self._topic = parts[1] if len(parts) > 1 else "default"
        self._producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
        self._consumer = AIOKafkaConsumer(
            self._topic, bootstrap_servers=bootstrap, group_id=self._kwargs.get("group_id")
        )
        await self._producer.start()
        await self._consumer.start()

    async def disconnect(self) -> None:
        await self._producer.stop()
        await self._consumer.stop()

    async def send(self, message: Any, **kwargs: Any) -> str | None:
        body = json.dumps(message).encode() if not isinstance(message, bytes) else message
        future = await self._producer.send(self._topic, value=body, **kwargs)
        result = await future
        return str(result.offset)

    async def receive(self, **kwargs: Any) -> dict | None:
        msg = await self._consumer.getone()
        if msg is None:
            return None
        body = msg.value.decode()
        return {
            "id": f"{msg.partition}:{msg.offset}",
            "body": json.loads(body) if body.startswith(("{", "[")) else body,
            "_raw": msg,
        }

    async def delete(self, message: Any) -> None:
        pass  # Kafka offsets are managed automatically via group_id
