"""FastAPI application for simulation-db API."""

from pathlib import Path
import os
from fastapi import APIRouter
from src.core.config import DATA_DIR

router = APIRouter()

@router.get("/get-stations")
def get_stations():
    files = os.listdir(DATA_DIR)
    stations = [f for f in files if f.startswith("stations")]
    return {"stations": stations}

@router.get("/get-shapes")
def get_shapes():
    files = os.listdir(DATA_DIR)
    shapes = [f for f in files if f.endswith(".geojson")]
    return {"shapes": shapes}

