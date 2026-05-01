"""Redis pub/sub bridge for live scan progress events.

Workers and the API publish events to channel `scan:{scan_id}`.
The WebSocket endpoint subscribes and forwards JSON events to clients.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import redis.asyncio as redis

from cobweb.core.settings import get_settings


def _channel(scan_id: str) -> str:
    return f"scan:{scan_id}"


_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def publish_scan_event(scan_id: str, event: dict[str, Any]) -> None:
    r = get_redis()
    await r.publish(_channel(scan_id), json.dumps(event))


async def subscribe_scan(scan_id: str) -> AsyncIterator[dict[str, Any]]:
    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(_channel(scan_id))
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                yield json.loads(message["data"])
            except json.JSONDecodeError:
                continue
    finally:
        await pubsub.unsubscribe(_channel(scan_id))
        await pubsub.aclose()
