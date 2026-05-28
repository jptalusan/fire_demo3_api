"""Stations / shapes file listing."""

import os

from fastapi import APIRouter, Depends

from backend.services.auth import get_current_user
from core.config import DATA_DIR

router = APIRouter()


@router.get("/get-stations")
def get_stations(_user: int = Depends(get_current_user)) -> dict:
    files = os.listdir(DATA_DIR)
    return {"stations": [f for f in files if f.startswith("stations")]}


@router.get("/get-shapes")
def get_shapes(_user: int = Depends(get_current_user)) -> dict:
    files = os.listdir(DATA_DIR)
    return {"shapes": [f for f in files if f.endswith(".geojson")]}
