"""Regression / audit-tracking for error response shapes on the incidents
routes.

Some of these already return a well-formed 4xx + JSON `detail` today (plain
assertions). Others are known to currently return a bare 500
'Internal Server Error' (text/plain, Starlette's default unhandled-exception
handler) -- surfaced in the earlier endpoint audit and NOT yet fixed. Those
are marked xfail(strict=False) with a NOTE explaining the current broken
behavior and what to flip the assertion to once someone fixes the route.
"""

from __future__ import annotations

import pytest

PROCESS_URL = "/api/incidents/process-incidents"
GENERATE_URL = "/api/incidents/generate-incidents"


# ---------------------------------------------------------------------------
# process-incidents
# ---------------------------------------------------------------------------

def test_process_incidents_empty_body_returns_4xx_with_detail(authed_client):
    resp = authed_client.post(PROCESS_URL, content=b"", headers={"Content-Type": "text/csv"})
    assert 400 <= resp.status_code < 500, resp.text
    assert "detail" in resp.json()


@pytest.mark.xfail(
    reason="NOTE(audit): garbage (non-CSV) bytes make pandas.read_csv produce a "
    "1-column frame with no 'incident_type' column; the route's subsequent "
    "df['incident_type'] access raises an unhandled KeyError -> Starlette's "
    "default 500 handler returns text/plain 'Internal Server Error' with no "
    "JSON body. Flip to a real assertion (status in (400, 422) and 'detail' "
    "in body) once process_incidents wraps parsing in a try/except.",
    strict=False,
)
def test_process_incidents_garbage_bytes_returns_4xx_with_detail(authed_client):
    resp = authed_client.post(PROCESS_URL, content=b"not a csv", headers={"Content-Type": "text/csv"})
    assert resp.status_code in (400, 422), resp.text
    assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# generate-incidents
# ---------------------------------------------------------------------------

def test_generate_incidents_missing_date_range_returns_422_with_detail(authed_client):
    resp = authed_client.post(GENERATE_URL, json={"incident_type": "fire"})
    assert resp.status_code == 422, resp.text
    assert "detail" in resp.json()


@pytest.mark.xfail(
    reason="NOTE(audit): GenerateIncidentsRequest.date_range fields are plain "
    "`str` -- no date-format validation -- so 'not-a-date' passes pydantic and "
    "crashes deep inside the growth_v1 pipeline (pd.Timestamp parsing) with an "
    "unhandled exception -> bare 500. Flip to a real assertion (4xx + 'detail') "
    "once the schema validates date format or the route catches the parse error.",
    strict=False,
)
def test_generate_incidents_malformed_date_returns_4xx_with_detail(authed_client, monkeypatch):
    # Mock the growth_v1 entry point instead of loading the real bundle: raise
    # the same exception type pd.Timestamp("not-a-date") raises in the real
    # pipeline, so this stays a fast, deterministic unit test while still
    # proving the route doesn't catch it.
    import backend.routes.incidents as incidents_route

    def _boom(*args, **kwargs):
        raise ValueError("could not convert string to Timestamp: 'not-a-date'")

    monkeypatch.setattr(incidents_route, "predict_incidents_growth_v1", _boom)

    resp = authed_client.post(GENERATE_URL, json={
        "date_range": {"start": "not-a-date", "end": "not-a-date"},
        "incident_type": "fire",
        "model": "growth_v1",
    })
    assert resp.status_code in (400, 422), resp.text
    assert "detail" in resp.json()


@pytest.mark.xfail(
    reason="NOTE(audit): when the growth_v1 bundle is absent, "
    "_load_default_payload raises FileNotFoundError which is unhandled by the "
    "route -> bare 500. Expected behavior: 503 with a body naming the missing "
    "bundle path. Flip once generate_incidents catches this and returns 503.",
    strict=False,
)
def test_generate_incidents_missing_bundle_returns_503_naming_path(authed_client, monkeypatch):
    import backend.routes.incidents as incidents_route

    missing_path = "/fake/data/models/growth_poisson_v1/growth_poisson_v1.pkl"

    def _boom(*args, **kwargs):
        raise FileNotFoundError(f"default model not found: {missing_path}")

    monkeypatch.setattr(incidents_route, "predict_incidents_growth_v1", _boom)

    resp = authed_client.post(GENERATE_URL, json={
        "date_range": {"start": "2025-01-01", "end": "2025-01-02"},
        "incident_type": "fire",
        "model": "growth_v1",
    })
    assert resp.status_code == 503, resp.text
    assert missing_path in resp.text
