"""
Redis Pub/Sub publisher. Used to broadcast events across multiple
realtime_service worker processes — e.g. when a negotiation message or
dashboard update needs to reach a WebSocket connection that may be held
by a different process/pod than the one that received the originating
event.
"""
import json
import logging

import redis.asyncio as aioredis

from realtime_service.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_client: aioredis.Redis | None = None


async def get_redis_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def publish_event(channel: str, payload: dict) -> None:
    """Publishes a JSON-serializable payload to a Redis Pub/Sub channel."""
    client = await get_redis_client()
    try:
        await client.publish(channel, json.dumps(payload))
    except Exception as exc:
        logger.error("Failed to publish to channel %s: %s", channel, exc)


def negotiation_channel(negotiation_id: str) -> str:
    return f"negotiation:{negotiation_id}"


def dashboard_channel(startup_id: str) -> str:
    return f"dashboard:{startup_id}"


def user_notification_channel(user_id: str) -> str:
    return f"notifications:{user_id}"