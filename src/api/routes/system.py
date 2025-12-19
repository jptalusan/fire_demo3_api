"""FastAPI application for simulation-db API."""

from fastapi import APIRouter

router = APIRouter()

@router.get("/health", tags=["system"])
async def health():
    """Health check endpoint."""
    return {"status": "ok"}