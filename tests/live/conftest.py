"""Shared config + fixtures for tests/live.

Everything in tests/live hits a real running backend. The `base_url`,
`bearer_token`, `http`, and `submit_and_wait` fixtures give each test a
consistent, session-scoped set of tools:

- `base_url` — resolved from LIVE_BASE_URL (default http://localhost:8000).
- `http` — a thin `urlopen`-based client returning (status, json/bytes).
- `bearer_token` — one portal-login per test session, cached.
- `submit_and_wait` — POST /api/jobs then poll to terminal state.

If the server isn't reachable at collection time, every test skips with a
clear message (not fails), so `pytest tests/` in a normal dev run doesn't
blow up when the docker stack is off.
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

import pytest


# --------------------------------------------------------------------------- #
# Config knobs (see tests/live/README.md)
# --------------------------------------------------------------------------- #

BASE_URL = os.environ.get("LIVE_BASE_URL", "http://localhost:8000").rstrip("/")
USERNAME = os.environ.get("LIVE_USERNAME", "livetest")
PASSWORD = os.environ.get("LIVE_PASSWORD", "livetest-password-123")
SIM_START = os.environ.get("LIVE_SIM_START", "2024-03-01")
SIM_END = os.environ.get("LIVE_SIM_END", "2024-03-03")
INCIDENT_TYPE = os.environ.get("LIVE_INCIDENT_TYPE", "ems_fire")
JOB_TIMEOUT_S = float(os.environ.get("LIVE_JOB_TIMEOUT_S", "600"))


# --------------------------------------------------------------------------- #
# Auto-skip if server isn't reachable
# --------------------------------------------------------------------------- #

def _server_reachable(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, socket.timeout, ConnectionError):
        return False


def pytest_collection_modifyitems(config, items):
    """If /health is unreachable, mark every collected test as skipped."""
    if _server_reachable(BASE_URL):
        return
    skip = pytest.mark.skip(
        reason=(
            f"live server at {BASE_URL} not reachable. Set LIVE_BASE_URL to a "
            f"running backend, or bring up docker: `docker compose up -d`."
        )
    )
    for item in items:
        item.add_marker(skip)


# --------------------------------------------------------------------------- #
# HTTP client
# --------------------------------------------------------------------------- #

class HttpClient:
    """Thin urlopen wrapper. Returns (status_int, body_json_or_bytes)."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
        headers: dict[str, str] | None = None,
        expect_json: bool = True,
        timeout: float = 30.0,
    ) -> tuple[int, Any]:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        data: bytes | None = None
        h: dict[str, str] = dict(headers or {})
        if json_body is not None:
            data = json.dumps(json_body).encode()
            h.setdefault("Content-Type", "application/json")
        elif raw_body is not None:
            data = raw_body
            if content_type:
                h.setdefault("Content-Type", content_type)
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status = r.status
                body = r.read()
        except urllib.error.HTTPError as e:
            status = e.code
            body = e.read()
        if expect_json:
            try:
                return status, json.loads(body) if body else None
            except json.JSONDecodeError:
                return status, body
        return status, body

    def get(self, path: str, **kw):
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw):
        return self.request("POST", path, **kw)

    def with_bearer(self, token: str) -> "HttpClient":
        return _BearerClient(self.base_url, token)


class _BearerClient(HttpClient):
    def __init__(self, base_url: str, token: str):
        super().__init__(base_url)
        self._token = token

    def request(self, method: str, path: str, *, headers: dict | None = None, **kw):
        h = dict(headers or {})
        h["Authorization"] = f"Bearer {self._token}"
        return super().request(method, path, headers=h, **kw)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def http() -> HttpClient:
    return HttpClient(BASE_URL)


@pytest.fixture(scope="session")
def bearer_token(http: HttpClient) -> str:
    """One portal-login per session. Raises if the server rejects auth,
    so downstream tests fail loudly (server up but auth broken)."""
    status, body = http.post(
        "/auth/portal-login", json_body={"username": USERNAME}
    )
    if status != 200 or not isinstance(body, dict) or "access_token" not in body:
        raise RuntimeError(
            f"live suite bootstrap failed: portal-login returned "
            f"HTTP {status} body={body!r}. Check that PORTAL_AUTH_ENABLED=true "
            f"in the backend .env, and that the URL scheme matches."
        )
    return body["access_token"]


@pytest.fixture(scope="session")
def auth_http(http: HttpClient, bearer_token: str) -> HttpClient:
    """HttpClient that attaches the bearer token to every request."""
    return http.with_bearer(bearer_token)


# --------------------------------------------------------------------------- #
# Job helpers
# --------------------------------------------------------------------------- #

TERMINAL_STATES = {"done", "failed", "cancelled"}


def poll_job(auth_http: HttpClient, job_id: int, timeout: float = JOB_TIMEOUT_S) -> dict:
    """Poll /api/jobs/{id} until terminal (done/failed/cancelled) or timeout.
    Returns the final job dict."""
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        status, body = auth_http.get(f"/api/jobs/{job_id}")
        if status != 200 or not isinstance(body, dict):
            raise AssertionError(
                f"polling /api/jobs/{job_id} returned HTTP {status} body={body!r}"
            )
        last = body
        if body.get("status") in TERMINAL_STATES:
            return body
        time.sleep(2.0)
    raise AssertionError(
        f"job {job_id} did not reach terminal state within {timeout}s "
        f"(last status={last.get('status')})"
    )


@pytest.fixture
def submit_and_wait(auth_http: HttpClient):
    """`submit_and_wait(payload)` -> final job dict."""
    def _run(payload: dict, timeout: float = JOB_TIMEOUT_S) -> dict:
        status, body = auth_http.post("/api/jobs", json_body=payload)
        assert status == 201, (
            f"submit failed: HTTP {status} body={body!r}"
        )
        assert isinstance(body, dict) and "id" in body, (
            f"submit response missing 'id': {body!r}"
        )
        return poll_job(auth_http, body["id"], timeout=timeout)
    return _run


# --------------------------------------------------------------------------- #
# Payload builders (reused by simulation + comparison tests)
# --------------------------------------------------------------------------- #

def sim_config(
    dispatch: str = "nearest",
    disable_ems: bool = False,
    station_data: str = "default_stations",
    stations: list[dict] | None = None,
    incident_type: str = INCIDENT_TYPE,
    start: str = SIM_START,
    end: str = SIM_END,
) -> dict:
    """Build a SimConfig-shaped payload with sensible test defaults."""
    p = {
        "models": {
            "incident": "historical_incidents",
            "travelTime": "OSRM",
            "serviceTime": "ml_based",
        },
        "date_range": {"start_date": start, "end_date": end},
        "incident_type": incident_type,
        "dispatch_policy": dispatch,
        "station_data": station_data,
        "disable_ems": disable_ems,
    }
    if stations is not None:
        p["stations"] = stations
    return p
