"""Integration tests for /api/incidents.

Engine functions are monkeypatched so the real simulator / data files / network
are never touched.
"""

import pandas as pd
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


def test_get_incidents_missing_dates_400(client, auth_headers, monkeypatch):
    # Empty start/end should 400 before touching the engine.
    monkeypatch.setattr(inc_mod, "get_or_create_historical_incidents", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))
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
    csv_file = tmp_path / "hist.csv"
    csv_file.write_text("incident_id,incident_type\n1,fire\n")
    monkeypatch.setattr(inc_mod, "get_or_create_historical_incidents", lambda *a, **k: str(csv_file))
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
    assert "incident_id" in r.text


def test_get_incidents_engine_value_error_400(client, auth_headers, monkeypatch):
    def boom(*a, **k):
        raise ValueError("no incidents in range")
    monkeypatch.setattr(inc_mod, "get_or_create_historical_incidents", boom)
    r = client.post(
        "/api/incidents/get-incidents",
        headers=auth_headers,
        json={"model_id": "historical_incidents", "filters": {
            "date_range": {"start": "2024-06-01", "end": "2024-06-02"},
            "incident_type": "fire",
        }},
    )
    assert r.status_code == 400
    assert "no incidents" in r.json()["detail"]


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

def test_generate_incidents_maps_params_and_returns_csv(client, auth_headers, monkeypatch, tmp_path):
    captured = {}

    def fake_growth(start_date, end_date, seed=42, incident_type="fire"):
        captured["start"] = start_date
        captured["end"] = end_date
        captured["seed"] = seed
        captured["incident_type"] = incident_type
        return pd.DataFrame([
            {"incident_id": 1, "lat": 36.1, "lon": -86.7, "incident_type": "fire",
             "datetime": "2024-06-01T00:00:00", "category": "structure"},
        ])

    # Redirect cache dir into tmp so nothing writes to real data dir.
    monkeypatch.setattr(inc_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(inc_mod, "predict_incidents_growth_v1", fake_growth)

    r = client.post(
        "/api/incidents/generate-incidents",
        headers=auth_headers,
        json={"date_range": {"start": "2024-06-01", "end": "2024-06-02"},
              "incident_type": "fire", "model": "growth_v1", "seed": 7},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "incident_id,lat,lon" in r.text
    assert captured["seed"] == 7
    assert captured["incident_type"] == "fire"


def test_generate_incidents_legacy_model(client, auth_headers, monkeypatch, tmp_path):
    def fake_legacy(start_date, end_date, incident_type="fire"):
        return pd.DataFrame([
            {"incident_id": 9, "lat": 1.0, "lon": 2.0, "incident_type": "fire",
             "incident_level": "Low", "datetime": "2024-06-01T00:00:00", "category": "x"},
        ])
    monkeypatch.setattr(inc_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(inc_mod, "predict_incidents_with_types_and_coordinates", fake_legacy)
    r = client.post(
        "/api/incidents/generate-incidents",
        headers=auth_headers,
        json={"date_range": {"start": "2024-06-01", "end": "2024-06-02"},
              "incident_type": "fire", "model": "legacy", "seed": 1},
    )
    assert r.status_code == 200
    assert "9," in r.text


# ---------- auth required ----------

@pytest.mark.parametrize("path", [
    "/api/incidents/get-incidents",
    "/api/incidents/process-incidents",
    "/api/incidents/generate-incidents",
])
def test_incidents_require_auth(client, path):
    r = client.post(path, json={})
    assert r.status_code == 401
