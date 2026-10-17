"""Mandatory autograder interface /audit/v1/* (spec section 5). Thin: parse -> service -> respond."""
from fastapi import APIRouter, Request

from .. import db
from ..http import read_json, respond
from ..seed import baseline
from ..services import scoring as scoring_svc
from ..validation import Fields, is_int

router = APIRouter(prefix="/audit/v1")


@router.post("/reset")
async def reset(request: Request):
    body = await read_json(request, optional=True)
    f = Fields()
    seed = body.get("seed", 42)
    if seed is None:
        seed = 42
    if not is_int(seed):
        f.add("seed")
    stock = body.get("stock") or {}
    if not isinstance(stock, dict) or not all(is_int(v) and v >= 0 for v in stock.values()):
        f.add("stock")
    f.check()
    async with db.tx() as conn:
        await db.lock(conn, "reset")
        result = await baseline.reset(conn, seed, stock)
    return respond(200, result)


@router.post("/sports")
async def create_sport(request: Request):
    return respond(201, await scoring_svc.create_sport(await read_json(request)))


@router.post("/events")
async def append_event(request: Request):
    status, resp = await scoring_svc.append_event(await read_json(request))
    return respond(status, resp)


@router.get("/score/{match_id}")
async def score(match_id: str):
    return respond(200, await scoring_svc.score(match_id))
