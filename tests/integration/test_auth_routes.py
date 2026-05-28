"""Integration tests for /auth routes."""


def test_register_then_login(client):
    r = client.post("/auth/register", json={"username": "eve", "password": "letmein1"})
    assert r.status_code == 201
    assert r.json()["username"] == "eve"

    r2 = client.post("/auth/login", json={"username": "eve", "password": "letmein1"})
    assert r2.status_code == 200
    body = r2.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_duplicate_register_conflicts(client):
    client.post("/auth/register", json={"username": "frank", "password": "letmein1"})
    r = client.post("/auth/register", json={"username": "frank", "password": "letmein1"})
    assert r.status_code == 409


def test_bad_password_rejected(client):
    client.post("/auth/register", json={"username": "gina", "password": "letmein1"})
    r = client.post("/auth/login", json={"username": "gina", "password": "wrong"})
    assert r.status_code == 401


def test_jobs_route_requires_auth(client):
    r = client.get("/api/jobs")
    assert r.status_code == 401
