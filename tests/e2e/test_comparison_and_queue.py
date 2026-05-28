"""E2E: comparison pipeline + global serialization gate through the full stack.

Uses a fake Simulator (no C++ binary / OSRM). Per-job log dirs are redirected to
a tmp path so real storage is never touched.
"""

import core.config as constants
from backend.services import simulator as sim_mod
from db import crud
from db.session import SessionLocal
from worker import processor as processor_mod
from worker.processor import process_job


class _FakeSim(sim_mod.Simulator):
    def __init__(self, raw):
        self.raw = raw

    async def run(self, req):
        return sim_mod.SimulatorRunResult(status=self.raw["status"], raw=self.raw)


def test_comparison_job_end_to_end(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(constants, "BASE_DIR", tmp_path)
    raw = {"status": "success", "average_response_time": 5.0, "coverage_percent": 80.0, "P90_continuous": 9.0}
    monkeypatch.setattr(processor_mod, "default_simulator", lambda: _FakeSim(raw))

    jid = client.post(
        "/api/jobs", headers=auth_headers,
        json={"kind": "run-comparison", "payload": {"baseline": {"a": 1}, "newConfig": {"b": 2}}},
    ).json()["id"]

    db = SessionLocal()
    try:
        claimed = crud.claim_next_pending_job(db, worker_id="test")
        process_job(db, claimed)
    finally:
        db.close()

    body = client.get(f"/api/jobs/{jid}", headers=auth_headers).json()
    assert body["status"] == "done"
    assert body["result"]["comparison"]["overall_metrics"]["average_response_time"]["baseline"] == 5.0
    assert body["duration_seconds"] is not None


def test_queue_serialization_through_stack(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(constants, "BASE_DIR", tmp_path)
    monkeypatch.setattr(processor_mod, "default_simulator", lambda: _FakeSim({"status": "success"}))

    j1 = client.post("/api/jobs", headers=auth_headers, json={"payload": {"n": 1}}).json()["id"]
    j2 = client.post("/api/jobs", headers=auth_headers, json={"payload": {"n": 2}}).json()["id"]

    db = SessionLocal()
    try:
        first = crud.claim_next_pending_job(db, worker_id="w1")
        assert first.id == j1
        # j1 is running -> j2 must not be claimable yet.
        assert crud.claim_next_pending_job(db, worker_id="w2") is None
        process_job(db, first)  # finish j1
        # Now j2 is claimable.
        second = crud.claim_next_pending_job(db, worker_id="w1")
        assert second.id == j2
        process_job(db, second)
    finally:
        db.close()

    assert client.get(f"/api/jobs/{j1}", headers=auth_headers).json()["status"] == "done"
    assert client.get(f"/api/jobs/{j2}", headers=auth_headers).json()["status"] == "done"
