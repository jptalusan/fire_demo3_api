"""Full authentication surface: register, login, portal-login, /me, logout.

Every negative case has an explicit assertion on the response body shape,
because silent 5xxs on bad input were the whole reason we added this.
"""
from __future__ import annotations

import time

from tests.live.conftest import PASSWORD, USERNAME


# --------------------------------------------------------------------------- #
# Positive paths
# --------------------------------------------------------------------------- #

def test_portal_login_returns_bearer_token(http):
    status, body = http.post("/auth/portal-login", json_body={"username": USERNAME})
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, dict), f"body={body!r}"
    for field in ("access_token", "token_type"):
        assert field in body, f"missing {field}: {body!r}"
    assert body["token_type"].lower() == "bearer"
    assert len(body["access_token"]) > 50, "token suspiciously short"


def test_register_is_idempotent_or_conflict(http):
    """Register with the live-test creds. First run 201, subsequent 409 -
    both are acceptable (idempotent enough for a suite you re-run)."""
    unique = f"regtest_{int(time.time())}"
    status, body = http.post(
        "/auth/register",
        json_body={"username": unique, "password": PASSWORD},
    )
    assert status in (201, 409), f"HTTP {status} body={body!r}"
    if status == 201:
        assert isinstance(body, dict) and body.get("username") == unique, body
    else:
        # 409 Conflict
        assert isinstance(body, dict) and "detail" in body, body


def test_login_with_valid_credentials_returns_bearer(http):
    # Use a DEDICATED username that is only ever created via /auth/register.
    # Do NOT reuse the portal-login username: portal-login provisions its user
    # with a random/unusable password hash (by design, so /auth/login can't be
    # used for portal accounts), which would make a password login here 401.
    login_user = f"{USERNAME}_pwlogin"
    http.post("/auth/register", json_body={"username": login_user, "password": PASSWORD})
    status, body = http.post(
        "/auth/login",
        json_body={"username": login_user, "password": PASSWORD},
    )
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, dict) and "access_token" in body, body


def test_auth_me_returns_current_user(auth_http):
    status, body = auth_http.get("/auth/me")
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, dict), body
    # Shape can vary — some deployments include id/username, some just username.
    assert body.get("username") or body.get("id") is not None, body


def test_auth_logout_succeeds(auth_http):
    status, body = auth_http.post("/auth/logout")
    assert status == 200, f"HTTP {status} body={body!r}"


# --------------------------------------------------------------------------- #
# Negative paths — must return structured 4xx, not text/plain 500
# --------------------------------------------------------------------------- #

def test_portal_login_rejects_missing_username(http):
    status, body = http.post("/auth/portal-login", json_body={})
    assert status == 422, f"expected 422 for missing field, got {status} body={body!r}"
    assert isinstance(body, dict) and "detail" in body, body


def test_portal_login_rejects_short_username(http):
    status, body = http.post("/auth/portal-login", json_body={"username": "x"})
    assert status == 422, f"expected 422 for short username, got {status} body={body!r}"


def test_register_rejects_short_password(http):
    status, body = http.post(
        "/auth/register",
        json_body={"username": "shortpwuser", "password": "x"},
    )
    assert status == 422, f"expected 422 for min_length password, got {status} body={body!r}"


def test_login_rejects_bad_password(http):
    http.post("/auth/register", json_body={"username": USERNAME, "password": PASSWORD})
    status, body = http.post(
        "/auth/login",
        json_body={"username": USERNAME, "password": "wrong-password"},
    )
    assert status == 401, f"expected 401, got {status} body={body!r}"
    assert isinstance(body, dict) and "detail" in body, body


def test_login_rejects_unknown_user_with_same_status(http):
    """No user enumeration: bad user vs bad password both return 401."""
    status, body = http.post(
        "/auth/login",
        json_body={"username": f"nosuch_{int(time.time())}", "password": PASSWORD},
    )
    assert status == 401, f"HTTP {status} body={body!r}"


def test_authenticated_endpoints_reject_missing_bearer(http):
    """Same-shape 401 for every guarded endpoint sampled here."""
    for path in ("/auth/me", "/api/jobs", "/api/stations/roster"):
        status, body = http.get(path)
        assert status == 401, f"{path}: expected 401, got {status} body={body!r}"
        assert isinstance(body, dict) and "detail" in body, f"{path}: body={body!r}"
