import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from . import config

log = logging.getLogger("nascon.db")
pool: AsyncConnectionPool | None = None


def dj(obj) -> str:
    """JSON for storage: ASCII-escaped so any string (even NUL) round-trips exactly through a TEXT column."""
    return json.dumps(obj, separators=(",", ":"))


def lj(s):
    return None if s is None else json.loads(s)


async def wait_for_db(timeout_s: int = 180) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        try:
            conn = await psycopg.AsyncConnection.connect(config.DATABASE_URL, connect_timeout=3)
            await conn.close()
            return
        except Exception as exc:  # noqa: BLE001
            if loop.time() > deadline:
                raise
            log.info("waiting for database: %s", exc)
            await asyncio.sleep(1)


async def open_pool() -> None:
    global pool
    await wait_for_db()
    pool = AsyncConnectionPool(config.DATABASE_URL, min_size=4, max_size=30, open=False,
                               kwargs={"row_factory": dict_row})
    await pool.open(wait=True, timeout=60)


async def close_pool() -> None:
    if pool is not None:
        await pool.close()


async def run_schema() -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text()
    async with tx() as conn:
        await conn.execute("SELECT pg_advisory_xact_lock(424242)")
        await conn.execute(sql)


@asynccontextmanager
async def tx():
    async with pool.connection() as conn:
        async with conn.transaction():
            yield conn


async def lock(conn, key: str) -> None:
    """Transaction-scoped advisory lock (released on commit/rollback)."""
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))


async def fetchone(conn, sql: str, params=()):
    cur = await conn.execute(sql, params)
    return await cur.fetchone()


async def fetchall(conn, sql: str, params=()):
    cur = await conn.execute(sql, params)
    return await cur.fetchall()


async def next_counter(conn, name: str) -> int:
    row = await fetchone(conn, "INSERT INTO counters(name, value) VALUES (%s, 1) "
                               "ON CONFLICT (name) DO UPDATE SET value = counters.value + 1 RETURNING value", (name,))
    return row["value"]


async def get_meta(conn, key: str, default=None):
    row = await fetchone(conn, "SELECT value FROM meta WHERE key=%s", (key,))
    return default if row is None else row["value"]
