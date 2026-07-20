"""Regression: the C++ simulator's incidents-CSV loader uses a naive
`line.split(',')` (no RFC-4180 quote-awareness). Quoting the writer's output
(csv.writer) is defense in depth, but the actual fix the simulator depends on
is that sanitize_incident_types removes every embedded comma BEFORE the row
is ever written -- root cause behind the datetime/category shift bugs fixed
in 0352dda / a795946 / 36cc7c1.

NOTE: data/incidents_export_apparatus.csv has already been through
sanitize_incident_types once historically -- as of writing this test, it
contains zero literal commas in incident_type (verified via
`df["incident_type"].str.contains(",").any()` and a raw grep over the file).
So we combine a sample of real historical (already-sanitized, no-comma) types
with synthetic-generator-style RAW comma types to exercise both the
passthrough path and the sanitize path through the same pipeline.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pandas as pd

from engine.incidents_variants import sanitize_incident_types

REPO_ROOT = Path(__file__).resolve().parents[3]
HISTORICAL_CSV = REPO_ROOT / "data" / "incidents_export_apparatus.csv"

DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

# Raw, un-sanitized incident_type values the growth_v1 generator can emit
# BEFORE sanitize_incident_types runs -- these DO contain literal commas.
RAW_COMMA_TYPES = [
    "Outside rubbish fire, other",
    "Public service assistance, other",
]


def _sample_historical_types(n: int = 5) -> list[str]:
    df = pd.read_csv(HISTORICAL_CSV, usecols=["incident_type"], nrows=5000)
    return list(df["incident_type"].dropna().unique()[:n])


def _build_fixture_df() -> pd.DataFrame:
    types = _sample_historical_types() + RAW_COMMA_TYPES
    n = len(types)
    return pd.DataFrame({
        "incident_id": list(range(n)),
        "lat": [36.1 + i * 0.001 for i in range(n)],
        "lon": [-86.1 - i * 0.001 for i in range(n)],
        "incident_type": types,
        "incident_level": ["Low"] * n,
        "datetime": ["2025-01-01 00:00:00"] * n,
        "category": ["Nine"] * n,
    })


def _write_like_production(df: pd.DataFrame) -> str:
    cols = ["incident_id", "lat", "lon", "incident_type", "incident_level", "datetime", "category"]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(cols)
    for _, row in df.iterrows():
        writer.writerow([row[c] for c in cols])
    return buf.getvalue()


def test_historical_csv_currently_has_no_literal_commas_in_incident_type():
    """Sanity check underpinning this test module's fixture design (see
    module docstring): if this ever starts failing, the historical CSV has
    regressed and the fixture below needs to change to sample real
    comma-containing rows directly instead of synthesizing RAW_COMMA_TYPES."""
    df = pd.read_csv(HISTORICAL_CSV, usecols=["incident_type"])
    assert not df["incident_type"].dropna().str.contains(",", regex=False).any()


def test_every_row_splits_to_seven_fields_under_naive_comma_split():
    df = _build_fixture_df()
    assert any("," in t for t in RAW_COMMA_TYPES), "fixture sanity check"

    sanitized = sanitize_incident_types(df)
    text = _write_like_production(sanitized)
    lines = [line for line in text.splitlines() if line]

    assert len(lines) == len(df) + 1  # header + rows
    for line in lines[1:]:
        fields = line.split(",")
        assert len(fields) == 7, f"naive split produced {len(fields)} fields: {line!r}"
        assert DATETIME_RE.match(fields[5]), f"datetime field malformed: {fields[5]!r}"
