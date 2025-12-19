"""FastAPI application for simulation-db API."""

from fastapi import APIRouter

router = APIRouter()

@router.get("/health", tags=["health"])
async def health():
    """Health check endpoint."""
    return {"status": "ok"}