"""Comparison job (run-comparison): baseline vs newConfig runs in parallel,
result carries both sides + a comparison block."""
from __future__ import annotations

from tests.live.conftest import sim_config


def test_run_comparison_completes_and_returns_both_sides(submit_and_wait):
    result = submit_and_wait({
        "kind": "run-comparison",
        "priority": 0,
        "payload": {
            "baseline":  sim_config(dispatch="nearest"),
            "newConfig": sim_config(dispatch="firebeats"),
        },
    })
    assert result["status"] == "done", (
        f"comparison did not finish: status={result.get('status')!r} "
        f"error={result.get('error')!r}"
    )
    r = result.get("result") or {}

    # Both legs must be present, with the same result shape as a single-sim job.
    for side in ("baseline", "newConfig"):
        assert side in r, f"result missing '{side}': keys={list(r.keys())}"
        leg = r[side]
        for k in ("total_incidents", "average_response_time",
                  "coverage_percent", "P90_continuous"):
            assert k in leg, f"{side}.{k} missing: {leg!r}"
            assert leg[k] is not None, f"{side}.{k} is None: {leg!r}"

    # Same incidents seen by both legs.
    assert r["baseline"]["total_incidents"] == r["newConfig"]["total_incidents"], (
        f"comparison sides saw different incident counts: "
        f"baseline={r['baseline']['total_incidents']} "
        f"newConfig={r['newConfig']['total_incidents']}"
    )


def test_run_comparison_progress_has_both_legs(auth_http, submit_and_wait):
    result = submit_and_wait({
        "kind": "run-comparison",
        "priority": 0,
        "payload": {
            "baseline":  sim_config(dispatch="nearest"),
            "newConfig": sim_config(dispatch="firebeats"),
        },
    })
    jid = result["id"]
    status, body = auth_http.get(f"/api/jobs/{jid}/progress")
    assert status == 200, f"HTTP {status} body={body!r}"
    legs = body.get("legs")
    assert isinstance(legs, dict) and len(legs) >= 2, (
        f"comparison progress should have baseline+newConfig legs: {legs!r}"
    )
    # Each leg has processed/total
    for name, leg in legs.items():
        assert "processed" in leg and "total" in leg, f"leg {name} missing counters: {leg!r}"
        assert leg["total"] > 0, f"leg {name} total is 0: {leg!r}"
