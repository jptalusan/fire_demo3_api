"""Integration tests for POST /auth/portal-login.

Asserts mechanisms, not just status codes:
  - Disabled (the default) returns 404 AND does not create the user in the DB.
  - Enabled creates the user on first call, reuses it on second.
  - The session it issues actually authenticates a subsequent /auth/me call.
  - A portal-created user CANNOT log in via /auth/login with any password
    (random unguessable password hash stored).
"""

import pytest

from backend.config import settings
from db import crud
from db.models import User
from db.session import SessionLocal


@pytest.fixture
def portal_enabled():
    """Flip the runtime feature flag for one test and restore it.

    This mutates a config value (data), not a method — same channel a real
    deployment uses via the PORTAL_AUTH_ENABLED env var.
    """
    prev = settings.PORTAL_AUTH_ENABLED
    settings.PORTAL_AUTH_ENABLED = True
    try:
        yield
    finally:
        settings.PORTAL_AUTH_ENABLED = prev


# ---------- disabled by default ----------

def test_portal_login_returns_404_when_flag_off(client):
    # Sanity: the feature must be off by default.
    assert settings.PORTAL_AUTH_ENABLED is False
    r = client.post("/auth/portal-login", json={"username": "wouldbeuser"})
    assert r.status_code == 404
    # And no user was created — the 404 must be a true no-op.
    db = SessionLocal()
    try:
        assert crud.get_user(db, "wouldbeuser") is None
    finally:
        db.close()


# ---------- enabled: happy paths ----------

def test_portal_login_creates_user_on_first_call(client, portal_enabled):
    db = SessionLocal()
    try:
        assert crud.get_user(db, "alice_portal") is None
    finally:
        db.close()

    r = client.post("/auth/portal-login", json={"username": "alice_portal"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]

    # User was actually persisted.
    db = SessionLocal()
    try:
        user = crud.get_user(db, "alice_portal")
        assert user is not None
        assert user.username == "alice_portal"
    finally:
        db.close()


def test_portal_login_reuses_existing_user(client, portal_enabled):
    # First call creates.
    first = client.post("/auth/portal-login", json={"username": "alice_again"})
    db = SessionLocal()
    try:
        first_id = crud.get_user(db, "alice_again").id
    finally:
        db.close()

    # Second call must NOT create a new user.
    second = client.post("/auth/portal-login", json={"username": "alice_again"})
    assert second.status_code == 200
    db = SessionLocal()
    try:
        second_user = crud.get_user(db, "alice_again")
        assert second_user.id == first_id
        # Exactly one user with that name.
        all_with_name = db.query(User).filter_by(username="alice_again").count()
        assert all_with_name == 1
    finally:
        db.close()


def test_portal_login_session_authenticates_subsequent_calls(client, portal_enabled):
    # Login -> /auth/me must succeed (proves the cookie / token is valid).
    client.post("/auth/portal-login", json={"username": "alice_session"})
    r = client.get("/auth/me")  # TestClient keeps the cookie jar
    assert r.status_code == 200
    assert r.json()["username"] == "alice_session"


# ---------- the security property: password login is impossible ----------

def test_portal_user_cannot_password_login_with_any_guess(client, portal_enabled):
    """A portal-created user has a high-entropy random password hash. The regular
    /auth/login must reject every reasonable guess."""
    client.post("/auth/portal-login", json={"username": "alice_pw"})
    for pw in ("", "password", "alice_pw", "1234567", "hunter2", "x" * 64):
        r = client.post("/auth/login", json={"username": "alice_pw", "password": pw})
        assert r.status_code == 401, f"password {pw!r} was accepted"


# ---------- validation ----------

def test_portal_login_rejects_short_username(client, portal_enabled):
    r = client.post("/auth/portal-login", json={"username": "ab"})
    assert r.status_code == 422
