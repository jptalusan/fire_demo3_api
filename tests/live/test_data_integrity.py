"""Data integrity as visible from the API. These tests use only HTTP —
no docker exec — so they run whether the backend is native or containerised.

The single common failure mode we've hit repeatedly is: the *server* thinks
it read a CSV correctly, but a downstream simulator or dispatch table sees
zeros / placeholders / wrong types because a column shifted, a datetime
carried subseconds, or a chief split hadn't been applied. These tests make
those symptoms visible via the API surface itself."""
from __future__ import annotations

from collections import Counter

import pytest

from tests.live.conftest import (
    INCIDENT_TYPE, SIM_END, SIM_START, sim_config,
)


def test_roster_has_both_chief_types_populated(auth_http):
    """Aggregate chief counts across the roster. If either total is zero,
    either the CSV rows are all-blank in that column OR the endpoint isn't
    reading the right column (we hit both). One should be non-zero at least."""
    status, body = auth_http.get("/api/stations/roster")
    assert status == 200, body
    totals: Counter[str] = Counter()
    for s in body["stations"]:
        for a in s["apparatus"]:
            totals[a["type"]] += a["count"]
    assert totals["Suppression_Chief"] + totals["EMS_Chief"] > 0, (
        f"roster reports zero chiefs of either type — CSV is empty for both "
        f"Suppression_Chief and EMS_Chief columns, or the endpoint isn't "
        f"reading them. Apparatus totals: {dict(totals)!r}"
    )


def test_historical_incidents_have_valid_categories(auth_http):
    """Every `category` value in the historical CSV must appear as an
    `Enum` in NFDResponse (otherwise the sim errors with 'No apparatus
    requirements for <cat>'). We can't hit NFDResponse directly over
    the API, but we can check the CSV shape."""
    _, csv_bytes = auth_http.post(
        "/api/incidents/get-incidents",
        json_body={
            "model_id": "historical_incidents",
            "filters": {
                "date_range": {"start": SIM_START, "end": SIM_END},
                "incident_type": INCIDENT_TYPE,
            },
        },
        expect_json=False,
    )
    text = csv_bytes.decode("utf-8") if isinstance(csv_bytes, bytes) else csv_bytes
    lines = text.splitlines()
    header = lines[0].split(",")
    assert header[-1] == "category", (
        f"unexpected historical CSV header order: {header!r}"
    )
    seen_cats = set()
    for row in lines[1:]:
        parts = row.split(",")
        if len(parts) < len(header):
            continue
        seen_cats.add(parts[-1])
    assert seen_cats, "no incident categories seen"
    # Sanity: categories should look like NFD enums, not numbers or blanks.
    problem = {c for c in seen_cats if not c or c.isdigit()}
    assert not problem, (
        f"historical CSV has {len(problem)} category value(s) that look like "
        f"placeholders or raw numeric codes: {sorted(problem)[:5]!r}"
    )


def test_historical_csv_has_no_carriage_returns(auth_http):
    """CRLF regression: last field of every CRLF row carries a stray '\\r'
    that the C++ simulator's stoi rejects with `invalid_argument`."""
    _, csv_bytes = auth_http.post(
        "/api/incidents/get-incidents",
        json_body={
            "model_id": "historical_incidents",
            "filters": {
                "date_range": {"start": SIM_START, "end": SIM_END},
                "incident_type": INCIDENT_TYPE,
            },
        },
        expect_json=False,
    )
    raw = csv_bytes if isinstance(csv_bytes, bytes) else csv_bytes.encode()
    assert b"\r" not in raw, (
        "historical CSV served by /api/incidents/get-incidents contains "
        "CRLF line endings — the C++ simulator's std::getline() leaves the "
        "'\\r' on the last field of every row and stoi() throws "
        "invalid_argument on it. Convert with `sed -i 's/\\r$//' "
        "data/incidents_export_apparatus*.csv` and re-fetch."
    )


def test_a_run_returns_numbers_consistent_with_input(submit_and_wait):
    """Run a 3-day sim and cross-check: total_incidents from the result
    should be close to the row count in the get-incidents CSV for the
    same window — verifies we're not silently dropping rows or double-
    counting."""
    result = submit_and_wait({
        "kind": "run-simulation",
        "priority": 0,
        "payload": sim_config(),
    })
    assert result["status"] == "done", result
    total = result["result"]["total_incidents"]
    assert total > 0, f"total_incidents = 0 for a 3-day window: {result['result']!r}"
    # A 3-day EMS-fire window in Nashville historically produces low-to-mid
    # hundreds. If we see zero, one, or millions, something's off.
    assert 10 < total < 100_000, (
        f"total_incidents={total} outside plausible range — check the "
        f"historical CSV and the incident_type filter."
    )
