"""Regression: GET /api/stations/roster must surface Suppression_Chief and
EMS_Chief counts.

Fixed in commit 4efcfff. Before the fix, backend/routes/stations.py's
CSV-column <-> payload-type lookup table did not know about the two new
chief columns, so `roster()` silently produced apparatus lists with no chief
entries at all -- a frontend round-tripping the roster into a job payload
would submit stations with zero chiefs.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.routes.stations as stations_route
from backend.main import app
from backend.services.auth import get_current_user

REAL_HEADER = (
    Path(__file__).resolve().parents[3] / "data" / "stations_with_apparatus.csv"
).read_text().splitlines()[0]
HEADER_COLS = REAL_HEADER.split(",")


def _make_roster_csv(rows: list[dict]) -> str:
    """Build a roster CSV using the REAL header, filling unspecified columns
    with '' (matching how the production CSVs represent "no apparatus")."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=HEADER_COLS)
    writer.writeheader()
    for row in rows:
        full = {c: "" for c in HEADER_COLS}
        full.update(row)
        writer.writerow(full)
    return buf.getvalue()


@pytest.fixture
def roster_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_text = _make_roster_csv([
        {
            "StationID": "0", "Stations": "Station 01", "lat": "36.1", "lon": "-86.1",
            "Nashville Fire Stations": "100 Main St",
            "Engine_ID": "1",
            "Suppression_Chief": "1", "EMS_Chief": "0",
        },
        {
            "StationID": "1", "Stations": "Station 02", "lat": "36.2", "lon": "-86.2",
            "Nashville Fire Stations": "200 Main St",
            "Engine_ID": "1",
            "Suppression_Chief": "0", "EMS_Chief": "2",
        },
    ])
    (data_dir / "stations_with_apparatus.csv").write_text(csv_text)
    return data_dir


@pytest.fixture
def roster_client(monkeypatch, roster_data_dir):
    monkeypatch.setattr(stations_route, "DATA_DIR", roster_data_dir)
    app.dependency_overrides[get_current_user] = lambda: 1
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


def test_roster_reports_suppression_chief_count(roster_client):
    resp = roster_client.get("/api/stations/roster")
    assert resp.status_code == 200, resp.text
    stations = {s["id"]: s for s in resp.json()["stations"]}

    station_0_apparatus = {a["type"]: a["count"] for a in stations["0"]["apparatus"]}
    assert station_0_apparatus.get("Suppression_Chief") == 1, (
        f"station 0 apparatus missing Suppression_Chief=1: {stations['0']['apparatus']}"
    )
    # count=0 apparatus entries are omitted entirely (matches _row_to_station's
    # `if count > 0` guard), not silently coerced to a phantom 0-count entry.
    assert "EMS_Chief" not in station_0_apparatus


def test_roster_reports_ems_chief_count(roster_client):
    resp = roster_client.get("/api/stations/roster")
    assert resp.status_code == 200, resp.text
    stations = {s["id"]: s for s in resp.json()["stations"]}

    station_1_apparatus = {a["type"]: a["count"] for a in stations["1"]["apparatus"]}
    assert station_1_apparatus.get("EMS_Chief") == 2, (
        f"station 1 apparatus missing EMS_Chief=2: {stations['1']['apparatus']}"
    )
    assert "Suppression_Chief" not in station_1_apparatus
