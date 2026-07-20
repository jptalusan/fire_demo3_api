"""Regression: sanitize_incident_types must strip commas from incident_type
using the historical ' -  ' (space-dash-two-spaces) convention.

Fixed in commit 0352dda ("Sanitize commas in synthetic incident_type, run
before remap_categories"). The C++ simulator's incidents CSV loader splits
on bare commas (no RFC-4180 quote-awareness), so any incident_type containing
a literal comma (e.g. 'Outside rubbish fire, other') shifted every following
column and crashed the loader. The replacement must also match the
historical incidents_export_apparatus.csv convention exactly (' -  ', not
' - ' or '-') so remap_categories's incident_type -> category lookup
(36cc7c1) actually finds these rows instead of falling back to a placeholder.
"""

from __future__ import annotations

import csv
import io

import pandas as pd

from engine.incidents_variants import sanitize_incident_types


def test_comma_containing_types_use_the_historical_dash_convention():
    df = pd.DataFrame({
        "incident_type": [
            "Outside rubbish fire, other",
            "Public service assistance, other",
        ]
    })
    out = sanitize_incident_types(df)
    assert list(out["incident_type"]) == [
        "Outside rubbish fire -  other",
        "Public service assistance -  other",
    ]


def test_output_incident_type_never_contains_a_comma():
    df = pd.DataFrame({"incident_type": ["Outside rubbish fire, other", "A, b, c", "No comma here"]})
    out = sanitize_incident_types(df)
    assert not out["incident_type"].str.contains(",", regex=False).any()


def test_historical_types_without_commas_pass_through_unchanged():
    historical = ["Medical", "Structure fire", "Dispatched and cancelled en route"]
    df = pd.DataFrame({"incident_type": historical})
    out = sanitize_incident_types(df)
    assert list(out["incident_type"]) == historical


def test_full_csv_row_parses_to_seven_columns_under_naive_comma_split():
    """Simulates the C++ loader's naive `line.split(',')` -- the actual
    mechanism that made unsanitized commas dangerous."""
    df = pd.DataFrame({
        "incident_id": [1, 2],
        "lat": [36.1, 36.2],
        "lon": [-86.1, -86.2],
        "incident_type": ["Outside rubbish fire, other", "Public service assistance, other"],
        "incident_level": ["Low", "High"],
        "datetime": ["2025-01-01 00:00:00", "2025-01-01 01:00:00"],
        "category": ["Major", "Unknown"],
    })
    sanitized = sanitize_incident_types(df)
    cols = ["incident_id", "lat", "lon", "incident_type", "incident_level", "datetime", "category"]

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(cols)
    for _, row in sanitized.iterrows():
        writer.writerow([row[c] for c in cols])
    text = buf.getvalue()

    lines = [line for line in text.splitlines() if line]
    assert len(lines) == len(df) + 1  # header + rows
    for line in lines[1:]:
        assert len(line.split(",")) == 7, f"naive split produced != 7 columns: {line!r}"
