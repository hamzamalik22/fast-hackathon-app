"""Internal job-queue worker: consumes the Redis Stream "domain-events" and persists every event."""
import asyncio
import json
import logging

import psycopg
import redis.asyncio as aioredis

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker: %(message)s")
log = logging.getLogger("nascon.worker")
STREAM, GROUP, CONSUMER = "domain-events", "workers", "worker-1"


async def main() -> None:
    r = aioredis.from_url(config.REDIS_URL)
    while True:
        try:
            await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
            break
        except Exception as exc:  # noqa: BLE001
            if "BUSYGROUP" in str(exc):
                break
            log.info("waiting for redis: %s", exc)
            await asyncio.sleep(1)
    conn = None
    while True:
        try:
            if conn is None or conn.closed:
                conn = await psycopg.AsyncConnection.connect(config.DATABASE_URL, autocommit=True)
            batches = await r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=50, block=5000)
            for _stream, entries in batches or []:
                for entry_id, fields in entries:
                    etype = fields.get(b"type", b"unknown").decode()
                    payload = fields.get(b"payload", b"{}").decode()
                    await conn.execute("INSERT INTO domain_event_log(type, payload) VALUES (%s, %s)",
                                       (etype, payload))
                    await r.xack(STREAM, GROUP, entry_id)
                    log.info("processed %s %s", etype, json.loads(payload).get("order_id", ""))
        except Exception as exc:  # noqa: BLE001
            log.warning("worker loop error: %s", exc)
            conn = None
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
