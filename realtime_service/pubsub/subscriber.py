"""
Redis Pub/Sub subscriber helpers. Each WebSocket connection subscribes
to its relevant channel(s) and forwards messages to the connected client.
"""
import asyncio
import json
import logging

import redis.asyncio as aioredis

from realtime_service.config import get_settings
from realtime_service.pubsub.publisher import get_redis_client

logger = logging.getLogger(__name__)
settings = get_settings()


class ChannelSubscriber:
    """
    Wraps a Redis Pub/Sub subscription for a single channel and exposes
    an async generator of decoded JSON messages. One instance per
    WebSocket connection — cleans up on disconnect.
    """

    def __init__(self, channel: str):
        self.channel = channel
        self._pubsub: aioredis.client.PubSub | None = None

    async def __aenter__(self):
        client = await get_redis_client()
        self._pubsub = client.pubsub()
        await self._pubsub.subscribe(self.channel)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(self.channel)
                await self._pubsub.aclose()
            except Exception as exc:
                logger.warning("Error closing subscription to %s: %s", self.channel, exc)

    async def listen(self):
        """Async generator yielding decoded JSON message payloads."""
        if not self._pubsub:
            raise RuntimeError("Subscriber not entered as a context manager.")
        async for message in self._pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                yield json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                logger.warning("Could not decode pubsub message on %s", self.channel)
                continue