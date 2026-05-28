"""End-to-end: submit a job, run one worker tick with a fake simulator, fetch result.

This avoids the real C++ binary by monkeypatching `default_simulator` to a fake.
Marked `slow` only because it exercises the full pipeline; still <1s.
"""

import pytest

from backend.services import simulator as sim_mod
from db import crud
from db.session import SessionLocal
from worker import processor as processor_mod
from worker.processor import process_job


class FakeSim(sim_mod.Simulator):
    async def run(self, req):
        return sim_mod.SimulatorRunResult(
            status="success",
            raw={"status": "success", "total_incidents": 7, "average_response_time": 4.2},
        )


def test_full_job_pipeline(client, auth_headers, monkeypatch):
    monkeypatch.setattr(processor_mod, "default_simulator", lambda: FakeSim())

    r = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"kind": "run-simulation", "payload": {"config": {"k": "v"}}},
    )
    assert r.status_code == 201
    job_id = r.json()["id"]

    db = SessionLocal()
    try:
        claimed = crud.claim_next_pending_job(db, worker_id="test")
        assert claimed.id == job_id
        process_job(db, claimed)
    finally:
        db.close()

    r2 = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
    body = r2.json()
    assert body["status"] == "done"
    assert body["result"]["total_incidents"] == 7
