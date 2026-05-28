"""Integration tests for /auth: cookie session, /me, /logout, validation, bad tokens."""

from datetime import datetime, timedelta, timezone

from jose import jwt

from backend.config import settings
from backend.services import auth as auth_svc


def _register(client, username="user1", password="password123"):
    return client.post("/auth/register", json={"username": username, "password": password})


# ---------- register validation ----------

def test_register_success_returns_201_and_id(client):
    r = _register(client, "newuser", "password123")
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "newuser"
    assert "id" in body


def test_register_short_username_422(client):
    r = client.post("/auth/register", json={"username": "ab", "password": "password123"})
    assert r.status_code == 422


def test_register_short_password_422(client):
    r = client.post("/auth/register", json={"username": "validname", "password": "short"})
    assert r.status_code == 422


# ---------- login ----------

def test_login_sets_cookie_and_returns_token(client):
    _register(client, "cookieuser", "password123")
    r = client.post("/auth/login", json={"username": "cookieuser", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["access_token"]
    # HttpOnly auth cookie set.
    assert "auth_token" in r.cookies or any(
        c.name == "auth_token" for c in client.cookies.jar
    )


def test_login_nonexistent_user_401(client):
    r = client.post("/auth/login", json={"username": "ghost", "password": "password123"})
    assert r.status_code == 401


def test_login_wrong_password_401(client):
    _register(client, "wp", "password123")
    r = client.post("/auth/login", json={"username": "wp", "password": "wrongpass1"})
    assert r.status_code == 401


# ---------- /auth/me ----------

def test_me_with_cookie_session(client):
    _register(client, "meuser", "password123")
    client.post("/auth/login", json={"username": "meuser", "password": "password123"})
    # TestClient persists the cookie; no explicit header needed.
    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "meuser"


def test_me_with_bearer_header(client):
    _register(client, "bearer", "password123")
    token = client.post("/auth/login", json={"username": "bearer", "password": "password123"}).json()["access_token"]
    fresh = client.__class__(client.app)  # new client with no cookies
    r = fresh.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "bearer"


def test_me_without_session_401(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_tampered_token_401(client):
    bad = "Bearer not.a.valid.jwt"
    r = client.get("/auth/me", headers={"Authorization": bad})
    assert r.status_code == 401


def test_me_bad_signature_token_401(client):
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "totally-wrong-secret",
        algorithm=auth_svc.ALGORITHM,
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_me_expired_token_401(client):
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    token = jwt.encode(
        {"sub": "1", "exp": past, "iat": past},
        settings.SECRET_KEY,
        algorithm=auth_svc.ALGORITHM,
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_me_valid_token_for_deleted_user_401(client, db_session):
    """A token whose user no longer exists -> 401 (me checks the user row)."""
    token = auth_svc.create_token(user_id=424242)  # no such user
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ---------- /auth/logout ----------

def test_logout_clears_cookie(client):
    _register(client, "loguser", "password123")
    client.post("/auth/login", json={"username": "loguser", "password": "password123"})
    r = client.post("/auth/logout")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    # Cookie deletion is signalled in the response headers.
    set_cookie = r.headers.get("set-cookie", "")
    assert "auth_token=" in set_cookie
