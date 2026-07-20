"""Incident endpoints: historical get, process, synthetic generate."""
from __future__ import annotations

import pytest

from tests.live.conftest import INCIDENT_TYPE, SIM_END, SIM_START


HISTORICAL_HEADER = "incident_id,lat,lon,incident_type,incident_level,datetime,category"


# --------------------------------------------------------------------------- #
# /api/incidents/get-incidents — historical replay CSV
# --------------------------------------------------------------------------- #

def test_get_incidents_historical_returns_csv(auth_http):
    status, body = auth_http.post(
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
    assert status == 200, f"HTTP {status} body preview={body[:200]!r}"
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    first_line = text.splitlines()[0]
    assert first_line == HISTORICAL_HEADER, (
        f"unexpected CSV header: {first_line!r}"
    )
    row_count = text.count("\n")
    assert row_count > 1, f"empty CSV body (only header): {text!r}"


def test_get_incidents_rejects_missing_filters(auth_http):
    status, body = auth_http.post("/api/incidents/get-incidents", json_body={})
    assert status == 422, f"HTTP {status} body={body!r}"


def test_get_incidents_rejects_bogus_model_id(auth_http):
    status, body = auth_http.post(
        "/api/incidents/get-incidents",
        json_body={
            "model_id": "not_a_real_model",
            "filters": {
                "date_range": {"start": SIM_START, "end": SIM_END},
                "incident_type": INCIDENT_TYPE,
            },
        },
    )
    assert status == 422, f"HTTP {status} body={body!r}"


def test_get_incidents_far_future_returns_error_body(auth_http):
    """An out-of-range window should error with a structured JSON body,
    not a text/plain 500. Some deployments 400, others 200 with empty."""
    status, body = auth_http.post(
        "/api/incidents/get-incidents",
        json_body={
            "model_id": "historical_incidents",
            "filters": {
                "date_range": {"start": "3000-01-01", "end": "3000-01-03"},
                "incident_type": INCIDENT_TYPE,
            },
        },
    )
    assert status in (200, 400), f"HTTP {status} body={body!r}"
    if status == 400:
        assert isinstance(body, dict) and "detail" in body, body


# --------------------------------------------------------------------------- #
# /api/incidents/process-incidents — stats from a CSV blob
# --------------------------------------------------------------------------- #

def test_process_incidents_returns_stats(auth_http):
    # Pull a real CSV, then hand it right back.
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
    status, body = auth_http.post(
        "/api/incidents/process-incidents",
        raw_body=csv_bytes,
        content_type="text/csv",
    )
    assert status == 200, f"HTTP {status} body={body!r}"
    for k in ("status", "incident_counts", "average_time_between_incidents_minutes",
              "total_incidents"):
        assert k in body, f"missing {k}: {body!r}"
    assert body["status"] == "success"
    assert isinstance(body["incident_counts"], dict) and body["incident_counts"]
    assert body["total_incidents"] > 0


def test_process_incidents_rejects_empty_body(auth_http):
    status, body = auth_http.post(
        "/api/incidents/process-incidents",
        raw_body=b"",
        content_type="text/csv",
    )
    # Empty is caught by the app (400) or by fastapi (422). Both are fine —
    # what matters is that it's a structured JSON error, not text/plain 500.
    assert status in (400, 422), f"HTTP {status} body={body!r}"
    assert isinstance(body, dict) and "detail" in body, body


# --------------------------------------------------------------------------- #
# /api/incidents/generate-incidents — synthetic (predictive, growth_v1)
# --------------------------------------------------------------------------- #

def test_generate_incidents_synthetic_returns_csv_or_503(auth_http):
    """If the growth_poisson_v1 model bundle is on the box, the endpoint
    returns a CSV. If not, it should still fail structurally — 503 or 400
    with a JSON detail, NOT a text/plain 500."""
    status, body = auth_http.post(
        "/api/incidents/generate-incidents",
        json_body={
            "date_range": {"start": "2027-01-01", "end": "2027-01-03"},
            "incident_type": INCIDENT_TYPE,
        },
        expect_json=False,
    )
    if status == 200:
        text = body.decode("utf-8") if isinstance(body, bytes) else body
        assert text.splitlines()[0] == HISTORICAL_HEADER, (
            f"synthetic CSV header mismatch: {text.splitlines()[0]!r}"
        )
        # Datetime + category checks — the two regression bugs we shipped.
        rows = text.splitlines()[1:]
        for r in rows[:5]:
            parts = r.split(",")
            assert len(parts) == 7, f"row has wrong column count: {r!r}"
            _, _, _, itype, _, dt, cat = parts
            assert "," not in itype, f"comma in incident_type: {r!r}"
            assert "." not in dt, f"fractional-second datetime: {r!r}"
            assert cat not in ("Major", "Unknown"), (
                f"placeholder category not remapped: {r!r}"
            )
    elif status in (400, 500, 503):
        # If it's a JSON error, we accept. If it's text/plain, that's the bug.
        assert not isinstance(body, bytes) or body.startswith(b"{"), (
            f"generate-incidents returned non-JSON error body (HTTP {status}): "
            f"{body[:120]!r} — should be structured JSON with a detail hint."
        )
    else:
        pytest.fail(f"unexpected HTTP {status} body={body!r}")
