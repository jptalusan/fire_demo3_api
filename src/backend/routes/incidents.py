"""Incidents endpoints: query historical, process uploaded, generate synthetic."""

import csv
import hashlib
import io
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import Response

import core.config as constants
from backend.schemas.incidents import (
    GenerateIncidentsRequest,
    GetIncidentsRequest,
    ProcessIncidentsResponse,
)
from backend.services.auth import get_current_user
from engine.incidents import predict_incidents_with_types_and_coordinates
from engine.incidents_variants import (
    predict_incidents as predict_incidents_growth_v1,
    remap_categories,
)
from engine.simulation import get_or_create_historical_incidents

router = APIRouter()
DATA_DIR = constants.DATA_DIR


@router.post("/get-incidents")
async def get_incidents(payload: GetIncidentsRequest, _user: int = Depends(get_current_user)) -> Response:
    if payload.model_id != "historical_incidents":
        raise HTTPException(status_code=400, detail="Only historical_incidents model is supported")

    filters = payload.filters.model_dump()
    date_range = filters.get("date_range") or {}
    start_date, end_date = date_range.get("start"), date_range.get("end")
    incident_type = filters.get("incident_type")
    if not start_date or not end_date:
        raise HTTPException(status_code=400, detail="Date range with start and end dates is required")

    try:
        query_path = get_or_create_historical_incidents(start_date, end_date, incident_type, DATA_DIR)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    csv_content = Path(query_path).read_text()
    return Response(content=csv_content, media_type="text/csv")


@router.post("/process-incidents", response_model=ProcessIncidentsResponse)
async def process_incidents(
    csv_data: str = Body(..., media_type="text/csv"),
    _user: int = Depends(get_current_user),
):
    if not csv_data.strip():
        raise HTTPException(status_code=400, detail="No CSV data provided")
    df = pd.read_csv(io.StringIO(csv_data))
    incident_counts = df["incident_type"].value_counts().to_dict()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime")
    deltas = df["datetime"].diff().dt.total_seconds() / 60.0
    deltas = deltas.dropna()
    avg = float(deltas.mean()) if len(deltas) else 0.0
    return {
        "status": "success",
        "incident_counts": incident_counts,
        "average_time_between_incidents_minutes": avg,
        "total_incidents": len(df),
    }


@router.post("/generate-incidents")
async def generate_incidents(
    payload: GenerateIncidentsRequest,
    _user: int = Depends(get_current_user),
) -> Response:
    start_date, end_date = payload.date_range.start, payload.date_range.end
    if not start_date or not end_date:
        raise HTTPException(status_code=400, detail="startDate and endDate are required")
    incident_type = payload.incident_type
    model_name = payload.model
    seed = payload.seed

    start_date_str = start_date[:10] if "T" in start_date else start_date
    end_date_str = end_date[:10] if "T" in end_date else end_date
    cache_key = f"synthetic_incidents_{model_name}_{start_date_str}_{end_date_str}_seed{seed}"
    query_hash = hashlib.md5(cache_key.encode()).hexdigest()
    query_filename = f"synthetic_{model_name}_{start_date_str}_{end_date_str}_{query_hash[:8]}.csv"
    query_dir = DATA_DIR / "incidents" / "synthetic" / incident_type / "query"
    query_dir.mkdir(parents=True, exist_ok=True)
    query_path = query_dir / query_filename

    if query_path.exists():
        csv_content = query_path.read_text()
        return Response(content=csv_content, media_type="text/csv")

    if model_name == "growth_v1":
        df = predict_incidents_growth_v1(start_date, end_date, seed=seed, incident_type=incident_type)
        if not df.empty:
            rng = np.random.default_rng(seed)
            df = df.copy()
            df["incident_level"] = rng.choice(["Low", "Moderate", "High"], size=len(df), p=[0.4, 0.4, 0.2])
        predicted = df
    else:
        predicted = predict_incidents_with_types_and_coordinates(start_date, end_date, incident_type=incident_type)

    # Replace placeholder categories ('Major', 'Unknown') with the canonical
    # NFDResponse Enum so the C++ simulator's dispatch table lookup matches.
    predicted = remap_categories(predicted)

    # The C++ simulator's datetime parser only accepts 'YYYY-MM-DD HH:MM:SS'.
    # Strip any fractional seconds before serialising; nanosecond timestamps
    # like '2027-01-01 00:03:47.463952217' otherwise fall through the parser
    # and the row mis-aligns from there.
    if not predicted.empty and "datetime" in predicted.columns:
        predicted = predicted.copy()
        predicted["datetime"] = pd.to_datetime(predicted["datetime"]).dt.strftime("%Y-%m-%d %H:%M:%S")

    incidents = predicted.to_dict("records") if not predicted.empty else []
    # Write RFC-4180 CSV via csv.writer so incident_type values that contain
    # commas (e.g. "Public service assistance, other") are quoted rather than
    # spilling into extra columns and corrupting the row.
    cols = ["incident_id", "lat", "lon", "incident_type", "incident_level", "datetime", "category"]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(cols)
    for i in incidents:
        writer.writerow([i[c] for c in cols])
    csv_content = buf.getvalue()
    query_path.write_text(csv_content)
    return Response(content=csv_content, media_type="text/csv")
