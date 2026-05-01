"""RabbitMQ publisher for scan jobs.

Phase 1 uses a single durable queue `cobweb.scans.nuclei`. Workers consume directly.
"""

from __future__ import annotations

import json
from typing import Any

import aio_pika

from cobweb.core.settings import get_settings

SCAN_QUEUE_NUCLEI = "cobweb.scans.nuclei"
SCAN_QUEUE_ZAP = "cobweb.scans.zap"


class QueuePublisher:
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None

    async def connect(self) -> None:
        if self._connection is None or self._connection.is_closed:
            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()
            for q in (SCAN_QUEUE_NUCLEI, SCAN_QUEUE_ZAP):
                await self._channel.declare_queue(q, durable=True)

    async def publish(self, queue: str, payload: dict[str, Any]) -> None:
        await self.connect()
        assert self._channel is not None
        message = aio_pika.Message(
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._channel.default_exchange.publish(message, routing_key=queue)

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()


_publisher: QueuePublisher | None = None


def get_publisher() -> QueuePublisher:
    global _publisher
    if _publisher is None:
        _publisher = QueuePublisher(get_settings().rabbitmq_url)
    return _publisher
