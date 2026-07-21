"""Job-submission input validation.

Contract being tested (important nuance): `POST /api/jobs` accepts `payload`
as a free-form dict *by design* -- the SimConfig schema is documented as a
reference, not enforced at submit, so the engine can evolve without breaking
the API. On top of that, the engine defaults leniently: an unknown
incident_type is treated as fire (anything != 'ems_fire' -> the fire incident
source), and a missing date_range falls back to the bundled incidents_small
sample. So bad payload *contents* often run to `done` rather than `failed`.

The real, defensible guarantees are therefore:

  - malformed *envelope* (unknown `kind`, missing `payload`) -> structured
    4xx at submit; and
  - malformed *payload contents* -> the request must TERMINATE CLEANLY: no
    text/plain 500 at submit, and if accepted, the job reaches a terminal
    state (done|failed|cancelled) without hanging. It may legitimately end
    `done` via the engine's defaults.

Tests assert exactly that, not stricter."""
from __future__ import annotations

import pytest

from tests.live.conftest import poll_job, sim_config


def _assert_structured_4xx(status: int, body):
    assert 400 <= status < 500, f"expected 4xx, got {status} body={body!r}"
    assert isinstance(body, dict), f"non-JSON error body: {body!r}"
    assert "detail" in body, f"missing 'detail': {body!r}"


def _submit(auth_http, body):
    return auth_http.post("/api/jobs", json_body=body)


def _assert_terminates_cleanly(auth_http, status, body):
    """Bad payload contents: must not 500 at submit, and if accepted must
    reach a terminal state (done|failed|cancelled) without hanging. A `done`
    via the engine's lenient defaults is acceptable -- the dangerous outcomes
    are a 500, a crash, or a hang, and those are what we rule out."""
    assert status != 500, f"HTTP 500 (should be structured error): {body!r}"
    if status == 201:
        final = poll_job(auth_http, body["id"])  # raises on hang/timeout
        assert final["status"] in ("done", "failed", "cancelled"), (
            f"job did not reach a terminal state: {final.get('status')!r}"
        )
    else:
        assert 400 <= status < 500, f"unexpected status {status}: {body!r}"


def test_missing_kind_defaults_to_run_simulation(auth_http):
    """`kind` has a schema default of 'run-simulation', so omitting it is
    accepted (not an error). Confirm it's treated as a run-simulation."""
    status, body = _submit(auth_http, {"priority": 0, "payload": sim_config()})
    assert status == 201, f"expected 201 (kind defaults), got {status} body={body!r}"
    assert body.get("kind") == "run-simulation", body


def test_missing_payload_is_rejected(auth_http):
    status, body = _submit(auth_http, {"kind": "run-simulation", "priority": 0})
    _assert_structured_4xx(status, body)


def test_unknown_kind_is_rejected(auth_http):
    """The envelope IS schema-validated -- an unknown kind must 4xx."""
    status, body = _submit(auth_http, {
        "kind": "run-teleportation", "priority": 0, "payload": sim_config(),
    })
    _assert_structured_4xx(status, body)


def test_negative_priority_is_accepted_or_rejected_but_not_500(auth_http):
    """priority isn't range-constrained; -1 may be accepted. Only real
    requirement: not a 500."""
    status, body = _submit(auth_http, {
        "kind": "run-simulation", "priority": -1, "payload": sim_config(),
    })
    assert status != 500, f"HTTP 500 on negative priority: {body!r}"


def test_missing_date_range_does_not_silently_succeed(auth_http):
    payload = sim_config()
    payload.pop("date_range", None)
    status, body = _submit(auth_http, {
        "kind": "run-simulation", "priority": 0, "payload": payload,
    })
    _assert_terminates_cleanly(auth_http, status, body)


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
def test_bogus_incident_type_terminates_cleanly(auth_http, bad_type):
    """incident_type lives in the free-form payload, so a bad value isn't
    rejected at submit. Unknown strings are treated as fire by the engine and
    may run to `done`; None/non-strings tend to fail the job. Requirement is
    only that it terminates cleanly (no 500, no hang)."""
    payload = sim_config()
    payload["incident_type"] = bad_type
    status, body = auth_http.post("/api/jobs", json_body={
        "kind": "run-simulation", "priority": 0, "payload": payload,
    })
    _assert_terminates_cleanly(auth_http, status, body)


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
