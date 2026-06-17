"""Integration tests for /api/incidents.

No engine functions are mocked or monkeypatched. The historical-incidents tests
run the REAL get_or_create_historical_incidents against real source CSVs written
into a temp data directory (DATA_DIR is redirected to tmp_path — config isolation
only, not a faked mechanism). The generate-incidents endpoint is covered
end-to-end (real engine + real data) by tests/test_incidents_route.py.
"""

import pytest

from backend.routes import incidents as inc_mod


def _auth(client, name="incuser"):
    client.post("/auth/register", json={"username": name, "password": "password123"})
    tok = client.post("/auth/login", json={"username": name, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


# ---------- get-incidents ----------

def test_get_incidents_rejects_non_historical_model(client, auth_headers):
    # model_id only allows 'historical_incidents' (pydantic Literal); anything else
    # is rejected with 422 before the route body runs.
    bad = client.post(
        "/api/incidents/get-incidents",
        headers=auth_headers,
        json={"model_id": "synthetic_incidents", "filters": {
            "date_range": {"start": "2024-06-01", "end": "2024-06-02"},
            "incident_type": "fire",
        }},
    )
    assert bad.status_code == 422


def test_get_incidents_missing_dates_400(client, auth_headers):
    # Empty start/end should 400. The route validates dates BEFORE calling the
    # engine (see get_incidents handler), so no fake/guard is needed — the real
    # short-circuit is what we exercise.
    r = client.post(
        "/api/incidents/get-incidents",
        headers=auth_headers,
        json={"model_id": "historical_incidents", "filters": {
            "date_range": {"start": "", "end": ""},
            "incident_type": "fire",
        }},
    )
    assert r.status_code == 400


def test_get_incidents_returns_csv(client, auth_headers, monkeypatch, tmp_path):
    # Real loader: write a real source file and let get_or_create_historical_incidents
    # filter it. DATA_DIR is redirected to tmp_path (config isolation only).
    source = tmp_path / "incidents_export_apparatus_fire.csv"
    source.write_text(
        "incident_id,incident_type,datetime\n"
        "1,fire,2024-06-01 12:00:00\n"
        "2,fire,2024-06-01 18:30:00\n"
    )
    monkeypatch.setattr(inc_mod, "DATA_DIR", tmp_path)

    r = client.post(
        "/api/incidents/get-incidents",
        headers=auth_headers,
        json={"model_id": "historical_incidents", "filters": {
            "date_range": {"start": "2024-06-01", "end": "2024-06-02"},
            "incident_type": "fire",
        }},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    # Both in-range rows survive the real date filter.
    assert "incident_id" in r.text
    assert "2024-06-01" in r.text
    assert r.text.count("\n") >= 3  # header + 2 rows (+ trailing)


def test_get_incidents_engine_value_error_400(client, auth_headers, monkeypatch, tmp_path):
    # Real loader raises ValueError when no incidents fall in the range. Source
    # rows are all OUTSIDE the queried window, so the real filter yields empty.
    source = tmp_path / "incidents_export_apparatus_fire.csv"
    source.write_text(
        "incident_id,incident_type,datetime\n"
        "1,fire,2020-01-01 12:00:00\n"
    )
    monkeypatch.setattr(inc_mod, "DATA_DIR", tmp_path)

    r = client.post(
        "/api/incidents/get-incidents",
        headers=auth_headers,
        json={"model_id": "historical_incidents", "filters": {
            "date_range": {"start": "2024-06-01", "end": "2024-06-02"},
            "incident_type": "fire",
        }},
    )
    assert r.status_code == 400
    assert "No incidents found" in r.json()["detail"]


# ---------- process-incidents ----------

def test_process_incidents_computes_stats(client, auth_headers):
    csv_data = (
        "incident_id,incident_type,datetime\n"
        "1,fire,2024-06-01T00:00:00\n"
        "2,ems,2024-06-01T00:10:00\n"
        "3,fire,2024-06-01T00:30:00\n"
    )
    r = client.post(
        "/api/incidents/process-incidents",
        headers={**auth_headers, "Content-Type": "text/csv"},
        content=csv_data,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["total_incidents"] == 3
    assert body["incident_counts"] == {"fire": 2, "ems": 1}
    # deltas: 10 and 20 minutes -> mean 15.
    assert body["average_time_between_incidents_minutes"] == pytest.approx(15.0)


def test_process_incidents_empty_400(client, auth_headers):
    r = client.post("/api/incidents/process-incidents", headers={**auth_headers, "Content-Type": "text/csv"}, content="   ")
    assert r.status_code == 400


# ---------- generate-incidents ----------
# Covered end-to-end (real engine + real data, no mocking) by
# tests/test_incidents_route.py: default==growth_v1, explicit growth_v1/legacy,
# incident_type filtering, caching/determinism, and CSV quoting. The previous
# monkeypatched stubs here (which replaced the real generators) were removed.


# ---------- auth required ----------

@pytest.mark.parametrize("path", [
    "/api/incidents/get-incidents",
    "/api/incidents/process-incidents",
    "/api/incidents/generate-incidents",
])
def test_incidents_require_auth(client, path):
    r = client.post(path, json={})
    assert r.status_code == 401
