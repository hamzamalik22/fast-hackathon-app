"""Fire-and-forget realtime publishing over Redis pub/sub. Never fails the request that triggered it."""
import json
import logging

from .. import config

log = logging.getLogger("nascon.realtime")
_redis = None


def client():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(config.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
    return _redis


async def publish(channel: str, message: dict) -> None:
    try:
        await client().publish(channel, json.dumps(message))
    except Exception as exc:  # noqa: BLE001
        log.debug("publish failed on %s: %s", channel, exc)


async def emit_domain_event(event_type: str, payload: dict) -> None:
    """Domain events go to the internal queue (Redis Stream), consumed by the worker."""
    try:
        await client().xadd("domain-events", {"type": event_type, "payload": json.dumps(payload)},
                            maxlen=10000, approximate=True)
    except Exception as exc:  # noqa: BLE001
        log.debug("xadd failed for %s: %s", event_type, exc)
