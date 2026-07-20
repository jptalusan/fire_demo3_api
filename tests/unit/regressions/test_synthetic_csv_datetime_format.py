"""Regression: synthetic-incident datetimes written to the simulator CSV must
be formatted 'YYYY-MM-DD HH:MM:SS' with no fractional seconds.

Fixed in commit a795946 ("Strip subseconds from synthetic incident
datetimes"). pd.Timestamp values carry nanosecond precision; serialising them
without `.dt.strftime(...)` produced strings like
'2027-01-01 00:03:47.463952217', which the C++ simulator's datetime parser
rejects, causing it to fall off the row and misread the next field.

We mock engine.incidents_variants.predict_incidents (no real growth_v1 bundle
load) and asyncio.create_subprocess_exec (no real C++ simulator), then run
engine.simulation.run_simulation_internal's synthetic_incidents branch for
real and inspect the CSV it wrote to disk.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

import engine.incidents_variants as variants
import engine.simulation as simulation

# `captured_subprocess_call` is a fixture provided by tests/unit/regressions/conftest.py
# (auto-discovered by pytest; no import needed).

DATETIME_LINE_RE = re.compile(
    r"^[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},[^,]+$"
)


def _nanosecond_precision_fixture_df() -> pd.DataFrame:
    return pd.DataFrame({
        "incident_id": [1, 2],
        "lat": [36.1, 36.2],
        "lon": [-86.1, -86.2],
        "incident_type": ["Medical", "Outside rubbish fire, other"],
        "category": ["Major", "Unknown"],
        # Nanosecond-precision timestamps -- the exact shape that broke the
        # C++ parser before a795946.
        "datetime": pd.to_datetime([
            "2027-01-01T00:03:47.463952217",
            "2027-01-01T01:15:00.000000001",
        ]),
    })


async def test_synthetic_csv_rows_have_no_fractional_seconds_in_datetime(
    tmp_path: Path, monkeypatch, captured_subprocess_call
):
    monkeypatch.setattr(variants, "predict_incidents", lambda *a, **k: _nanosecond_precision_fixture_df())

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    config = {
        "models": {"incident": "synthetic_incidents", "travelTime": "OSRM", "serviceTime": "ml_based"},
        "date_range": {"start_date": "2025-01-01", "end_date": "2025-01-02"},
        "incident_type": "fire",
        "seed": 42,
    }

    # Regardless of the final status (the mocked subprocess never produces
    # real report CSVs, so this returns status=error downstream) -- the
    # synthetic incidents CSV must already be on disk by the time the
    # simulator would have been invoked.
    await simulation.run_simulation_internal(config, data_dir, logs_dir, models_dir)

    query_dir = data_dir / "incidents" / "synthetic" / "query"
    csv_files = list(query_dir.glob("*.csv"))
    assert csv_files, f"no synthetic incidents CSV written under {query_dir}"

    text = csv_files[0].read_text()
    lines = [line for line in text.splitlines() if line]
    assert lines[0] == "incident_id,lat,lon,incident_type,incident_level,datetime,category"

    for line in lines[1:]:
        assert DATETIME_LINE_RE.match(line), (
            f"row does not match expected 'YYYY-MM-DD HH:MM:SS' datetime format: {line!r}"
        )
