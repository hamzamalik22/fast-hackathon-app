"""Realtime WebSocket: /api/v1/ws?token=<jwt>. Fans out Redis pub/sub (match:*, league:*) to subscribers."""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket

from .. import config
from ..errors import ApiError
from ..security import verify_token

log = logging.getLogger("nascon.ws")
router = APIRouter()


class Hub:
    def __init__(self):
        self.subs: dict[str, set[WebSocket]] = {}
        self.task: asyncio.Task | None = None

    def ensure_listener(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.get_running_loop().create_task(self._listen())

    async def _listen(self) -> None:
        import redis.asyncio as aioredis
        while True:
            try:
                r = aioredis.from_url(config.REDIS_URL)
                ps = r.pubsub()
                await ps.psubscribe("match:*", "league:*")
                async for msg in ps.listen():
                    if msg.get("type") != "pmessage":
                        continue
                    channel = msg["channel"].decode()
                    data = msg["data"].decode()
                    for ws in list(self.subs.get(channel, ())):
                        try:
                            await ws.send_text(data)
                        except Exception:  # noqa: BLE001
                            self.drop(ws)
            except Exception as exc:  # noqa: BLE001
                log.info("pubsub listener restarting: %s", exc)
                await asyncio.sleep(1)

    def add(self, ws: WebSocket, channel: str) -> None:
        self.subs.setdefault(channel, set()).add(ws)

    def drop(self, ws: WebSocket, channel: str | None = None) -> None:
        for ch in [channel] if channel else list(self.subs):
            self.subs.get(ch, set()).discard(ws)


hub = Hub()


@router.websocket("/api/v1/ws")
async def realtime_socket(ws: WebSocket, token: str = ""):
    try:
        verify_token(token)
    except ApiError:
        await ws.close(code=4401)
        return
    await ws.accept()
    hub.ensure_listener()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            channels = [c for c in msg.get("channels") or [] if isinstance(c, str)
                        and c.split(":", 1)[0] in ("match", "league") and len(c) <= 80]
            if msg.get("action") == "subscribe":
                for c in channels:
                    hub.add(ws, c)
                await ws.send_text(json.dumps({"type": "subscribed", "channels": channels}))
            elif msg.get("action") == "unsubscribe":
                for c in channels:
                    hub.drop(ws, c)
            elif msg.get("action") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except Exception:  # noqa: BLE001 - disconnects end the loop
        pass
    finally:
        hub.drop(ws)
