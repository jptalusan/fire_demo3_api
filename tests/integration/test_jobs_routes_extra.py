"""Integration tests for /api/jobs: submit kinds, progress, queue/status, 404s, auth."""

import pytest


def _headers_for(client, username):
    client.post("/auth/register", json={"username": username, "password": "password123"})
    tok = client.post("/auth/login", json={"username": username, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


# ---------- submit ----------

def test_submit_run_simulation_pending_with_position(client, auth_headers):
    r = client.post("/api/jobs", headers=auth_headers, json={"kind": "run-simulation", "payload": {"k": "v"}})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["kind"] == "run-simulation"
    assert body["queue_position"] == 1
    assert body["duration_seconds"] is None


def test_submit_run_comparison(client, auth_headers):
    r = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"kind": "run-comparison", "payload": {"baseline": {}, "newConfig": {}}},
    )
    assert r.status_code == 201
    assert r.json()["kind"] == "run-comparison"


def test_submit_default_kind_is_run_simulation(client, auth_headers):
    r = client.post("/api/jobs", headers=auth_headers, json={"payload": {"x": 1}})
    assert r.status_code == 201
    assert r.json()["kind"] == "run-simulation"


def test_submit_priority_orders_queue_position(client, auth_headers):
    low = client.post("/api/jobs", headers=auth_headers, json={"payload": {}, "priority": 0}).json()
    high = client.post("/api/jobs", headers=auth_headers, json={"payload": {}, "priority": 5}).json()
    # Re-fetch to get current positions.
    low_now = client.get(f"/api/jobs/{low['id']}", headers=auth_headers).json()
    high_now = client.get(f"/api/jobs/{high['id']}", headers=auth_headers).json()
    assert high_now["queue_position"] == 1
    assert low_now["queue_position"] == 2


# ---------- list ----------

def test_list_newest_first(client, auth_headers):
    a = client.post("/api/jobs", headers=auth_headers, json={"payload": {"n": 1}}).json()
    b = client.post("/api/jobs", headers=auth_headers, json={"payload": {"n": 2}}).json()
    jobs = client.get("/api/jobs", headers=auth_headers).json()
    ids = [j["id"] for j in jobs]
    assert ids.index(b["id"]) < ids.index(a["id"])


# ---------- get one / 404s ----------

def test_get_other_users_job_404(client):
    h1 = _headers_for(client, "owner1")
    h2 = _headers_for(client, "intruder1")
    jid = client.post("/api/jobs", headers=h1, json={"payload": {}}).json()["id"]
    assert client.get(f"/api/jobs/{jid}", headers=h2).status_code == 404


def test_get_missing_job_404(client, auth_headers):
    assert client.get("/api/jobs/999999", headers=auth_headers).status_code == 404


# ---------- progress ----------

def test_progress_shape_for_own_job(client, auth_headers):
    jid = client.post("/api/jobs", headers=auth_headers, json={"payload": {}}).json()["id"]
    r = client.get(f"/api/jobs/{jid}/progress", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == jid
    assert body["status"] == "pending"
    assert body["processed"] == 0 and body["total"] == 0
    assert body["percent"] == 0.0
    assert "simulation" in body["legs"]


def test_progress_comparison_legs(client, auth_headers):
    jid = client.post(
        "/api/jobs", headers=auth_headers,
        json={"kind": "run-comparison", "payload": {"baseline": {}, "newConfig": {}}},
    ).json()["id"]
    body = client.get(f"/api/jobs/{jid}/progress", headers=auth_headers).json()
    assert set(body["legs"]) == {"baseline", "newConfig"}


def test_progress_other_users_job_404(client):
    h1 = _headers_for(client, "powner")
    h2 = _headers_for(client, "pother")
    jid = client.post("/api/jobs", headers=h1, json={"payload": {}}).json()["id"]
    assert client.get(f"/api/jobs/{jid}/progress", headers=h2).status_code == 404


# ---------- queue/status ----------

def test_queue_status_shape(client, auth_headers):
    client.post("/api/jobs", headers=auth_headers, json={"payload": {}})
    r = client.get("/api/jobs/queue/status", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["pending_total"] == 1
    assert body["your_pending"] == 1
    assert body["your_next_position"] == 1
    assert body["running_total"] == 0


def test_queue_status_not_captured_as_job_id(client, auth_headers):
    """The /queue/status route must win over /{job_id} for 'queue'."""
    r = client.get("/api/jobs/queue/status", headers=auth_headers)
    assert r.status_code == 200  # not a 404/422 job lookup


# ---------- auth required on all /api/jobs ----------

@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/jobs"),
        ("post", "/api/jobs"),
        ("get", "/api/jobs/1"),
        ("get", "/api/jobs/1/progress"),
        ("get", "/api/jobs/queue/status"),
    ],
)
def test_jobs_endpoints_require_auth(client, method, path):
    fn = getattr(client, method)
    r = fn(path, json={"payload": {}}) if method == "post" else fn(path)
    assert r.status_code == 401
