"""FastAPI application for simulation-db API."""

from fastapi import APIRouter
from src.api.routes.engine import router as engine_router
from src.api.routes.incidents import router as incidents_router
from src.api.routes.stations import router as stations_router
from src.api.routes.system import router as systemsrouter

# TODO: separating database operations from the API route logic, making the code more maintainable and reusable.
api_router = APIRouter()
api_router.include_router(engine_router, prefix="/engine", tags=["engine"])
api_router.include_router(incidents_router, prefix="/incidents", tags=["incidents"])
api_router.include_router(stations_router, prefix="/stations", tags=["stations"])
api_router.include_router(systemsrouter, tags=["system"])