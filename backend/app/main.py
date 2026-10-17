import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db
from .api import audit, mobile, ws
from .errors import ApiError
from .http import BodyLimitMiddleware
from .security import RateLimitMiddleware
from .seed import baseline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("nascon")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.open_pool()
    await db.run_schema()
    await baseline.ensure_seeded()
    log.info("backend ready")
    yield
    await db.close_pool()


app = FastAPI(title="NaSCon League & Club Operations Platform", version="1.0.0", lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)  # inner: /api/v1/* only
app.add_middleware(BodyLimitMiddleware)  # outermost: 413 before anything else


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


def _err(status: int, code: str, message: str, details: dict | None = None, headers=None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": details or {}}},
                        status_code=status, headers=headers)


@app.exception_handler(ApiError)
async def api_error_handler(_req: Request, exc: ApiError):
    return JSONResponse(exc.body(), status_code=exc.status, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_req: Request, exc: RequestValidationError):
    fields = []
    for e in exc.errors():
        loc = [str(x) for x in e.get("loc", []) if x not in ("body", "query", "path")]
        if loc and loc[0] not in fields:
            fields.append(".".join(loc))
    return _err(400, "VALIDATION_ERROR", "Request validation failed.", {"fields": fields})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_req: Request, exc: StarletteHTTPException):
    codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    return _err(exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))


@app.exception_handler(Exception)
async def unhandled_handler(_req: Request, exc: Exception):
    log.exception("unhandled error: %s", exc)
    return _err(500, "INTERNAL_ERROR", "Something went wrong on our side.")


@app.get("/health")
async def health():
    try:
        async with db.tx() as conn:
            seeded = await db.get_meta(conn, "seeded") is not None
    except Exception:  # noqa: BLE001
        seeded = False
    if not seeded:
        return _err(503, "NOT_READY", "Database not reachable or not seeded yet.")
    return {"status": "ok"}


app.include_router(audit.router)
app.include_router(mobile.router)
app.include_router(ws.router)

_static = Path(__file__).parent / "static"
_static.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static)), name="static")
