"""FastAPI application entrypoint."""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from backend.config import ensure_runtime_dirs, settings
from backend.routes import auth, incidents, jobs, stations, system
from db.models import Base
from db.session import engine as db_engine

logger = logging.getLogger("fire_demo3_api_v2")

app = FastAPI(
    title="Fire Demo3 Backend v2",
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
)

# CORS — origins come from CORS_ALLOWED_ORIGINS (.env). With credentials enabled
# the spec forbids '*'; if you set CORS_ALLOWED_ORIGINS=* we disable credentials
# automatically so the middleware still works.
_allow_credentials = settings.CORS_ALLOWED_ORIGINS != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next) -> Response:
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    logger.info(f"{request.method} {request.url.path} - {elapsed:.4f}s")
    return response


# Public routes
app.include_router(system.router, tags=["system"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])

# API v1. Simulations run through the async job queue (/api/jobs); the old
# synchronous /api/engine routes were removed in favor of it.
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
app.include_router(stations.router, prefix="/api/stations", tags=["stations"])


@app.on_event("startup")
def on_startup() -> None:
    # storage/, logs/, data/ are gitignored — make sure they exist before we try
    # to open the SQLite file or write per-run logs. Without this, a fresh clone
    # crashes on first boot with "unable to open database file".
    ensure_runtime_dirs()
    logger.info("Creating database tables if missing.")
    Base.metadata.create_all(bind=db_engine)
