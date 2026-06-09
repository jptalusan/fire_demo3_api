"""Stations / shapes listing + roster contents."""

import csv
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.services.auth import get_current_user
from core.config import DATA_DIR

router = APIRouter()


# The default station roster lives in this file. Same column set the simulator
# writes for user-defined rosters via `create_stations_csv_from_payload`.
DEFAULT_ROSTER_FILE = "stations_with_apparatus.csv"
APPARATUS_COLUMNS = [
    "Engine_ID", "Truck", "Rescue", "Hazard", "Squad",
    "FAST", "Medic", "Brush", "Boat", "UTV", "REACH", "Chief",
]
# CSV column name -> apparatus type as used in the job payload.
_CSV_TO_TYPE = {c: ("Engine" if c == "Engine_ID" else c) for c in APPARATUS_COLUMNS}


@router.get("/get-stations")
def get_stations(_user: int = Depends(get_current_user)) -> dict:
    """List station-roster CSV filenames available on the server."""
    files = os.listdir(DATA_DIR)
    return {"stations": [f for f in files if f.startswith("stations")]}


@router.get("/get-shapes")
def get_shapes(_user: int = Depends(get_current_user)) -> dict:
    """List GeoJSON shape filenames available on the server."""
    files = os.listdir(DATA_DIR)
    return {"shapes": [f for f in files if f.endswith(".geojson")]}


@router.get("/roster")
def roster(
    _user: int = Depends(get_current_user),
    file: str = Query(
        DEFAULT_ROSTER_FILE,
        description="CSV filename under data/ to parse. Must start with 'stations' "
        "and live directly in data/ (no path traversal).",
    ),
) -> dict[str, Any]:
    """Return the contents of a station-roster CSV as JSON.

    Each station: `{id, name, address, lat, lon, apparatus: [{type, count}]}`.
    The apparatus shape matches the payload accepted by `POST /api/jobs` for
    custom stations, so a frontend can round-trip a roster into a job.
    """
    # Guardrail: no path traversal, must be a stations CSV directly under data/.
    if "/" in file or "\\" in file or not file.startswith("stations") or not file.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`file` must be a 'stations*.csv' filename in the data directory",
        )
    path = Path(DATA_DIR) / file
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"roster file not found: {file}",
        )

    stations: list[dict[str, Any]] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stations.append(_row_to_station(row))
    return {"file": file, "count": len(stations), "stations": stations}


def _row_to_station(row: dict[str, str]) -> dict[str, Any]:
    """Map one CSV row to the station shape the simulator and the frontend expect."""
    apparatus = []
    for col, type_name in _CSV_TO_TYPE.items():
        raw = (row.get(col) or "").strip()
        if not raw:
            continue
        try:
            count = int(raw)
        except ValueError:
            # Surface bad data rather than silently dropping it.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"apparatus count for {col!r} on station {row.get('StationID')!r} "
                       f"is not an integer: {raw!r}",
            )
        if count > 0:
            apparatus.append({"type": type_name, "count": count})

    return {
        "id": (row.get("StationID") or "").strip(),
        "name": (row.get("Stations") or "").strip(),
        "address": (row.get("Nashville Fire Stations") or "").strip(),
        "lat": _parse_coord(row, "lat"),
        "lon": _parse_coord(row, "lon"),
        "apparatus": apparatus,
    }


def _parse_coord(row: dict[str, str], key: str) -> float | None:
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{key} on station {row.get('StationID')!r} is not a number: {raw!r}",
        )
