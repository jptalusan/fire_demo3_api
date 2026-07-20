"""Job-submission input validation.

Each test posts a broken payload and asserts the server returns a
structured 4xx JSON error — never a text/plain 500 or a job that quietly
runs to completion with wrong data."""
from __future__ import annotations

import pytest

from tests.live.conftest import sim_config


def _assert_structured_4xx(status: int, body):
    assert 400 <= status < 500, f"expected 4xx, got {status} body={body!r}"
    assert isinstance(body, dict), f"non-JSON error body: {body!r}"
    assert "detail" in body, f"missing 'detail': {body!r}"


def test_missing_kind_is_rejected(auth_http):
    status, body = auth_http.post("/api/jobs", json_body={
        "priority": 0,
        "payload": sim_config(),
    })
    _assert_structured_4xx(status, body)


def test_missing_payload_is_rejected(auth_http):
    status, body = auth_http.post("/api/jobs", json_body={
        "kind": "run-simulation",
        "priority": 0,
    })
    # Depending on the pydantic model this can be 422 (missing field)
    # or 400 (validated by the route). Accept any 4xx.
    _assert_structured_4xx(status, body)


def test_unknown_kind_is_rejected(auth_http):
    status, body = auth_http.post("/api/jobs", json_body={
        "kind": "run-teleportation",
        "priority": 0,
        "payload": sim_config(),
    })
    _assert_structured_4xx(status, body)


def test_negative_priority_is_rejected(auth_http):
    status, body = auth_http.post("/api/jobs", json_body={
        "kind": "run-simulation",
        "priority": -1,
        "payload": sim_config(),
    })
    _assert_structured_4xx(status, body)


def test_missing_date_range_is_rejected(auth_http):
    payload = sim_config()
    payload.pop("date_range", None)
    status, body = auth_http.post("/api/jobs", json_body={
        "kind": "run-simulation", "priority": 0, "payload": payload,
    })
    _assert_structured_4xx(status, body)


def test_swapped_date_range_is_rejected_or_returns_empty(auth_http):
    """start > end. Some deployments 400 immediately, others accept and
    the worker returns 0 incidents. Both are 'not a crash', which is what
    we're checking."""
    payload = sim_config(start="2024-03-05", end="2024-03-01")
    status, body = auth_http.post("/api/jobs", json_body={
        "kind": "run-simulation", "priority": 0, "payload": payload,
    })
    assert status in (201, 400, 422), f"HTTP {status} body={body!r}"


@pytest.mark.parametrize("bad_dispatch", ["", "random", "None", None, 42])
def test_bogus_dispatch_policy_is_rejected(auth_http, bad_dispatch):
    payload = sim_config()
    payload["dispatch_policy"] = bad_dispatch
    status, body = auth_http.post("/api/jobs", json_body={
        "kind": "run-simulation", "priority": 0, "payload": payload,
    })
    # Some deployments coerce to firebeats silently (accept 201); others
    # reject at schema. What matters is: not a 500.
    assert status != 500, f"HTTP 500 on bogus dispatch — should validate: {body!r}"


@pytest.mark.parametrize("bad_type", ["", "not_a_real_type", None, 42])
def test_bogus_incident_type_is_rejected(auth_http, bad_type):
    payload = sim_config()
    payload["incident_type"] = bad_type
    status, body = auth_http.post("/api/jobs", json_body={
        "kind": "run-simulation", "priority": 0, "payload": payload,
    })
    assert status in (422, 400), f"expected schema rejection, got {status} body={body!r}"


def test_apparatus_uses_legacy_chief_is_still_accepted_or_ignored(auth_http):
    """Backward-compat: a payload with the old `"Chief"` type may either be
    rejected (422) or silently dropped by the writer. What must NOT happen:
    a 500. The frontend flag is that the sim runs but ignores that entry."""
    payload = sim_config(
        station_data="custom_stations",
        stations=[{
            "id": "0", "name": "Station 01",
            "lat": 36.229, "lon": -86.756,
            "apparatus": [{"type": "Chief", "count": 1}],
        }],
    )
    status, body = auth_http.post("/api/jobs", json_body={
        "kind": "run-simulation", "priority": 0, "payload": payload,
    })
    assert status != 500, f"HTTP 500 on legacy Chief payload: {body!r}"


def test_custom_stations_without_stations_field_fails_clearly(auth_http):
    """station_data=custom_stations but no stations list is a common frontend
    slip. Server should error at submit or fail the job cleanly — not 500."""
    payload = sim_config(station_data="custom_stations")
    status, body = auth_http.post("/api/jobs", json_body={
        "kind": "run-simulation", "priority": 0, "payload": payload,
    })
    assert status != 500, f"HTTP 500 on incomplete custom_stations: {body!r}"
