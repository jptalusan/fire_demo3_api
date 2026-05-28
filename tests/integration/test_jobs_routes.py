"""Integration tests for /api/jobs."""


def test_submit_and_list(client, auth_headers):
    r = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"kind": "run-simulation", "payload": {"foo": "bar"}, "priority": 0},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    job_id = body["id"]

    r2 = client.get("/api/jobs", headers=auth_headers)
    assert r2.status_code == 200
    assert any(j["id"] == job_id for j in r2.json())

    r3 = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
    assert r3.status_code == 200
    assert r3.json()["id"] == job_id


def test_other_users_cannot_see_each_others_jobs(client):
    client.post("/auth/register", json={"username": "helen", "password": "passpass"})
    client.post("/auth/register", json={"username": "harry", "password": "passpass"})
    t1 = client.post("/auth/login", json={"username": "helen", "password": "passpass"}).json()["access_token"]
    t2 = client.post("/auth/login", json={"username": "harry", "password": "passpass"}).json()["access_token"]

    r = client.post(
        "/api/jobs",
        headers={"Authorization": f"Bearer {t1}"},
        json={"kind": "run-simulation", "payload": {}},
    )
    job_id = r.json()["id"]
    r2 = client.get(f"/api/jobs/{job_id}", headers={"Authorization": f"Bearer {t2}"})
    assert r2.status_code == 404
