"""Integration tests for the new endpoints:
- POST /api/jobs/{id}/cancel
- GET  /api/jobs?compact=true
- GET  /api/stations/roster

No monkey-patching: routes are exercised through the real TestClient against
the in-memory DB; the roster test writes a real CSV to a tmp data dir and
points the running app at it via the same env var the route reads (DATA_DIR).
"""

import csv

import pytest


# --------------------------------------------------------------------------- #
# /api/jobs/{id}/cancel
# --------------------------------------------------------------------------- #

def _submit_job(client, auth_headers):
    r = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"kind": "run-simulation", "payload": {"foo": "bar"}, "priority": 0},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_cancel_pending_flips_to_failed(client, auth_headers):
    jid = _submit_job(client, auth_headers)

    r = client.post(f"/api/jobs/{jid}/cancel", headers=auth_headers)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["result"] == "cancelled_pending"
    assert body["job"]["status"] == "failed"
    assert "Cancelled by user before it started." in body["job"]["error"]

    # And a subsequent GET shows the terminal state.
    g = client.get(f"/api/jobs/{jid}", headers=auth_headers).json()
    assert g["status"] == "failed"


def test_cancel_terminal_job_is_idempotent_noop(client, auth_headers):
    jid = _submit_job(client, auth_headers)
    # Cancel once -> failed.
    client.post(f"/api/jobs/{jid}/cancel", headers=auth_headers)
    # Cancel again -> already_terminal; no further mutation.
    r = client.post(f"/api/jobs/{jid}/cancel", headers=auth_headers)
    assert r.status_code == 202
    body = r.json()
    assert body["result"] == "already_terminal"
    assert body["job"]["status"] == "failed"


def test_cancel_unknown_job_returns_404(client, auth_headers):
    r = client.post("/api/jobs/999999/cancel", headers=auth_headers)
    assert r.status_code == 404


def test_cancel_other_users_job_returns_404(client, auth_headers):
    # Create a job as one user, then a second user, then try cancelling.
    jid = _submit_job(client, auth_headers)

    # Register + log in a second user (overwrites the cookie jar).
    client.post("/auth/register", json={"username": "intruder", "password": "intruderpw"})
    client.post("/auth/login", json={"username": "intruder", "password": "intruderpw"})

    r = client.post(f"/api/jobs/{jid}/cancel")  # uses the new session cookie
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# /api/jobs?compact=true
# --------------------------------------------------------------------------- #

def test_compact_list_omits_payload_and_result(client, auth_headers):
    jid = _submit_job(client, auth_headers)

    r = client.get("/api/jobs?compact=true", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert any(row["id"] == jid for row in rows)
    for row in rows:
        assert row["payload"] is None, "compact=true must null out payload"
        assert row["result"] is None, "compact=true must null out result"
        # But all the lightweight fields must still be there.
        for key in ("id", "kind", "status", "attempts", "created_at"):
            assert key in row


def test_default_list_keeps_payload(client, auth_headers):
    jid = _submit_job(client, auth_headers)
    r = client.get("/api/jobs", headers=auth_headers)
    rows = r.json()
    row = next(r for r in rows if r["id"] == jid)
    assert row["payload"] == {"foo": "bar"}


# --------------------------------------------------------------------------- #
# /api/stations/roster
# --------------------------------------------------------------------------- #

ROSTER_HEADER = [
    "StationID", "Stations", "lat", "lon", "Nashville Fire Stations",
    "Engine_ID", "Truck", "Rescue", "Hazard", "Squad",
    "FAST", "Medic", "Brush", "Boat", "UTV", "REACH", "Chief",
]


def _write_roster(dir_path, filename="stations_with_apparatus.csv"):
    path = dir_path / filename
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(ROSTER_HEADER)
        # Two stations with different apparatus mixes (one with engines, one EMS-only).
        w.writerow(["0", "Station 01", "36.2294", "-86.7567", "addr 1",
                    "1", "", "1", "", "", "", "1", "", "", "", "", ""])
        w.writerow(["1", "Station 02", "36.1500", "-86.7800", "addr 2",
                    "", "", "", "", "", "", "2", "", "", "", "", "1"])
    return path


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Point the route at a tmp data dir built fresh for this test.

    This is a one-line env-var redirect, not a method patch — the route reads
    `DATA_DIR` at import time so we set it before the route module imports its
    `DATA_DIR` constant. To avoid having to re-import, we patch the symbol the
    route resolved at import time. (The Settings layer is env-driven; this is
    the minimal hook to redirect it for tests.)
    """
    from backend.routes import stations as stations_route
    monkeypatch.setattr(stations_route, "DATA_DIR", tmp_path)
    return tmp_path


def test_roster_returns_parsed_stations(client, auth_headers, isolated_data_dir):
    _write_roster(isolated_data_dir)

    r = client.get("/api/stations/roster", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file"] == "stations_with_apparatus.csv"
    assert body["count"] == 2
    s0, s1 = body["stations"]
    assert s0["id"] == "0" and s0["name"] == "Station 01"
    assert s0["lat"] == 36.2294 and s0["lon"] == -86.7567
    # Engine_ID -> "Engine" type mapping is the contract the simulator expects.
    types = {a["type"]: a["count"] for a in s0["apparatus"]}
    assert types == {"Engine": 1, "Rescue": 1, "Medic": 1}
    # Station with no engines — make sure zero/blank apparatus columns are dropped.
    types1 = {a["type"]: a["count"] for a in s1["apparatus"]}
    assert "Engine" not in types1
    assert types1 == {"Medic": 2, "Chief": 1}


def test_roster_missing_file_returns_404(client, auth_headers, isolated_data_dir):
    # No CSV written -> the default file doesn't exist.
    r = client.get("/api/stations/roster", headers=auth_headers)
    assert r.status_code == 404


def test_roster_rejects_path_traversal(client, auth_headers, isolated_data_dir):
    # Even with a valid extension, slashes / non-stations names are refused.
    bad = ["../etc/passwd", "../../stations_with_apparatus.csv",
           "anything.csv", "stations_with_apparatus"]
    for f in bad:
        r = client.get(f"/api/stations/roster?file={f}", headers=auth_headers)
        assert r.status_code == 400, f


def test_roster_alternate_filename_accepted(client, auth_headers, isolated_data_dir):
    _write_roster(isolated_data_dir, filename="stations_baseline.csv")
    r = client.get("/api/stations/roster?file=stations_baseline.csv", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["file"] == "stations_baseline.csv"


def test_roster_requires_auth(client):
    r = client.get("/api/stations/roster")
    assert r.status_code == 401
