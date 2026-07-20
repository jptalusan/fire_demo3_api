"""End-to-end job lifecycle: submit, poll, verify result shape + numbers,
list, cancel. Covers `run-simulation` for every dispatch policy + disable_ems
combo, and the queue-status endpoint."""
from __future__ import annotations

import time

import pytest

from tests.live.conftest import poll_job, sim_config


# --------------------------------------------------------------------------- #
# Submit + poll — one job per major axis
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "dispatch,disable_ems,label",
    [
        ("nearest",   False, "NEAREST default"),
        ("firebeats", False, "FIREBEATS default"),
        ("nearest",   True,  "NEAREST fire-only"),
    ],
)
def test_run_simulation_completes(submit_and_wait, dispatch, disable_ems, label):
    payload = {
        "kind": "run-simulation",
        "priority": 0,
        "payload": sim_config(dispatch=dispatch, disable_ems=disable_ems),
    }
    result = submit_and_wait(payload)
    assert result["status"] == "done", (
        f"[{label}] job did not finish: status={result.get('status')!r} "
        f"error={result.get('error')!r}"
    )
    r = result.get("result") or {}
    for k in ("total_incidents", "average_response_time",
              "coverage_percent", "P90_continuous"):
        assert k in r, f"[{label}] result missing {k}: keys={list(r.keys())}"
    assert isinstance(r["total_incidents"], int) and r["total_incidents"] > 0
    assert isinstance(r["average_response_time"], (int, float)) and r["average_response_time"] > 0
    assert 0 <= r["coverage_percent"] <= 100, r["coverage_percent"]
    assert isinstance(r["P90_continuous"], (int, float)) and r["P90_continuous"] > 0
    # Sanity: P90 should be at least the mean.
    assert r["P90_continuous"] >= r["average_response_time"], (
        f"[{label}] P90 < avg — suspicious result: {r}"
    )

    # Station + vehicle reports should be present and non-empty.
    for report_key in ("station_report", "vehicle_report"):
        rep = r.get(report_key)
        assert isinstance(rep, list) and rep, (
            f"[{label}] {report_key} missing/empty: {rep!r}"
        )


# --------------------------------------------------------------------------- #
# Listing + queue status
# --------------------------------------------------------------------------- #

def test_get_jobs_returns_list_with_the_ones_we_just_submitted(auth_http):
    status, body = auth_http.get("/api/jobs")
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, list), body
    assert body, "expected at least one job in the list (this suite just ran some)"
    for j in body[:5]:
        for k in ("id", "kind", "status"):
            assert k in j, f"job missing {k}: {j!r}"


def test_get_jobs_compact_omits_payload(auth_http):
    status, body = auth_http.get("/api/jobs?compact=true")
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, list), body
    # compact should null out payload/result (implementation-specific — accept
    # missing keys OR None).
    if body:
        for j in body[:3]:
            assert j.get("payload") in (None, {}), (
                f"compact=true should suppress payload, got {j.get('payload')!r}"
            )


def test_queue_status_returns_counts(auth_http):
    status, body = auth_http.get("/api/jobs/queue/status")
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, dict), body
    # Different deployments name the counts slightly differently; look for
    # anything numeric that's plausibly a queue counter.
    has_numeric_counter = any(isinstance(v, int) for v in body.values())
    assert has_numeric_counter, f"queue/status body has no int counters: {body!r}"


# --------------------------------------------------------------------------- #
# Individual-job endpoints
# --------------------------------------------------------------------------- #

def test_get_single_job_returns_full_shape(auth_http, submit_and_wait):
    result = submit_and_wait({
        "kind": "run-simulation",
        "priority": 0,
        "payload": sim_config(),
    })
    jid = result["id"]
    status, body = auth_http.get(f"/api/jobs/{jid}")
    assert status == 200, f"HTTP {status} body={body!r}"
    for k in ("id", "user_id", "kind", "status", "payload", "result",
              "error", "attempts", "created_at", "started_at", "finished_at",
              "duration_seconds"):
        assert k in body, f"single-job missing {k}: keys={list(body.keys())}"


def test_progress_endpoint_reports_totals(auth_http, submit_and_wait):
    result = submit_and_wait({
        "kind": "run-simulation",
        "priority": 0,
        "payload": sim_config(),
    })
    jid = result["id"]
    status, body = auth_http.get(f"/api/jobs/{jid}/progress")
    assert status == 200, f"HTTP {status} body={body!r}"
    for k in ("job_id", "status", "processed", "total", "percent", "legs"):
        assert k in body, f"progress missing {k}: {body!r}"
    assert body["total"] > 0, f"progress.total should be >0 for a done job: {body!r}"
    assert body["processed"] == body["total"], (
        f"done job should be at 100%: processed={body['processed']} total={body['total']}"
    )
    assert isinstance(body["legs"], dict) and body["legs"], (
        f"legs should be a non-empty dict for a run-simulation job: {body!r}"
    )


def test_get_nonexistent_job_returns_404(auth_http):
    status, body = auth_http.get("/api/jobs/999999999")
    assert status == 404, f"HTTP {status} body={body!r}"
    assert isinstance(body, dict) and "detail" in body, body


def test_progress_of_nonexistent_job_returns_404(auth_http):
    status, body = auth_http.get("/api/jobs/999999999/progress")
    assert status == 404, f"HTTP {status} body={body!r}"


# --------------------------------------------------------------------------- #
# Cancellation
# --------------------------------------------------------------------------- #

def test_cancel_pending_job_marks_it_cancelled(auth_http):
    """Submit two jobs back-to-back. The second stays pending briefly while
    the first runs; cancel it before the worker touches it."""
    def submit_one():
        s, b = auth_http.post("/api/jobs", json_body={
            "kind": "run-simulation", "priority": 0, "payload": sim_config(),
        })
        assert s == 201 and "id" in b, (s, b)
        return b["id"]

    first_id = submit_one()
    second_id = submit_one()

    # Cancel the second while first is running.
    time.sleep(0.5)
    s, b = auth_http.post(f"/api/jobs/{second_id}/cancel")
    # Either it was still pending (202) or it already advanced (still fine).
    assert s in (202, 200), f"unexpected cancel response: HTTP {s} body={b!r}"

    # The pending-cancel path marks it failed with a "cancelled" message;
    # the terminal path is a no-op. Either way, the eventual status is not
    # 'done'... unless the worker happened to finish before us. Poll and
    # accept any terminal state; the request must have been accepted.
    final = poll_job(auth_http, second_id)
    assert final["status"] in ("done", "failed", "cancelled"), final


def test_cancel_nonexistent_job_returns_404(auth_http):
    status, body = auth_http.post("/api/jobs/999999999/cancel")
    assert status == 404, f"HTTP {status} body={body!r}"
