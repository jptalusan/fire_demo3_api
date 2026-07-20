"""Regression: create_stations_csv_from_payload writer behavior.

Fixed in commit c76b35c ("Split Chief into Suppression_Chief + EMS_Chief in
the apparatus schema"). Pins:
  - Suppression_Chief / EMS_Chief counts land in the correct columns.
  - The 'Engine' -> 'Engine_ID' payload rename still works.
  - An apparatus type absent from the current schema (e.g. the legacy bare
    'Chief') is silently DROPPED from the output row. This is pinned as
    CURRENT behavior so that a future change to raise/warn instead is a
    deliberate, reviewed decision -- not an accidental regression either way.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from engine.simulation import create_stations_csv_from_payload

REAL_STATIONS_CSV = Path(__file__).resolve().parents[3] / "data" / "stations_with_apparatus.csv"

PAYLOAD = [
    {
        "id": "0", "name": "Station A", "lat": 36.1, "lon": -86.1,
        "apparatus": [
            {"type": "Suppression_Chief", "count": 2},
            {"type": "EMS_Chief", "count": 1},
        ],
    },
    {
        "id": "1", "name": "Station B", "lat": 36.2, "lon": -86.2,
        "apparatus": [
            {"type": "Engine", "count": 1},
            {"type": "Medic", "count": 1},
        ],
    },
    {
        "id": "2", "name": "Station C", "lat": 36.3, "lon": -86.3,
        # Not a real apparatus column in the current schema -- must be dropped.
        "apparatus": [{"type": "Chief", "count": 1}],
    },
]


@pytest.fixture
def written_rows(tmp_path):
    out_path = tmp_path / "user_stations.csv"
    create_stations_csv_from_payload(PAYLOAD, out_path)
    with open(out_path, newline="") as f:
        return list(csv.reader(f))


def test_header_matches_real_stations_csv_header_exactly(written_rows):
    header = ",".join(written_rows[0])
    real_header = REAL_STATIONS_CSV.read_text().splitlines()[0]
    assert header == real_header


def test_chief_counts_written_to_correct_columns(written_rows):
    header = written_rows[0]
    row0 = dict(zip(header, written_rows[1]))
    assert row0["Suppression_Chief"] == "2"
    assert row0["EMS_Chief"] == "1"


def test_engine_payload_type_renamed_to_engine_id_column(written_rows):
    header = written_rows[0]
    assert "Engine" not in header  # renamed away entirely, only Engine_ID exists
    row1 = dict(zip(header, written_rows[2]))
    assert row1["Engine_ID"] == "1"
    assert row1["Medic"] == "1"


def test_unrecognized_apparatus_type_is_silently_dropped(written_rows):
    header = written_rows[0]
    row2 = dict(zip(header, written_rows[3]))
    apparatus_cols = header[5:]  # everything after the 5 fixed identity columns
    for col in apparatus_cols:
        assert row2[col] == "", (
            f"expected apparatus column {col!r} to be empty for station C "
            f"(unrecognized 'Chief' type), got {row2[col]!r}"
        )
