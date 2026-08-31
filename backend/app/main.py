from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import init_db
from .events import broker
from .logging_setup import setup_logging
from .routers import (auth_routes, deals_routes, notify_routes, rules_routes,
                      sources_routes, system_routes)

setup_logging()
log = logging.getLogger("sparbit")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    broker.bind_loop(asyncio.get_running_loop())

    from . import scheduler as sched
    sched.start()
    log.info("SparBit gestartet")
    try:
        yield
    finally:
        await sched.shutdown()
        log.info("SparBit beendet")


app = FastAPI(title="SparBit", version="1.0.0",
              description="Selbstgehostete Deal- & Freebie-Zentrale",
              lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )

app.include_router(auth_routes.router)
app.include_router(sources_routes.router)
app.include_router(deals_routes.router)
app.include_router(rules_routes.router)
app.include_router(notify_routes.router)
app.include_router(notify_routes.quiet_router)
app.include_router(system_routes.router)
app.include_router(system_routes.sse_router)
app.include_router(system_routes.claimer_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unbehandelter Fehler bei %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500,
                        content={"detail": "Interner Fehler - siehe Logs."})
