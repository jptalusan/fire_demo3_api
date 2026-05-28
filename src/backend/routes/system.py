"""Health and version routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict:
    return {"name": "fire_demo3_api_v2", "version": "0.1.0"}
