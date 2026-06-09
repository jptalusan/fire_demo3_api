"""End-to-end: submit a job, run one worker tick with a fake simulator, fetch result.

The Simulator is injected via `sim_factory=` — no monkey-patching of module globals.
"""

from backend.services import simulator as sim_mod
from db import crud
from db.session import SessionLocal
from worker.processor import process_job


class FakeSim(sim_mod.Simulator):
    async def run(self, req):
        return sim_mod.SimulatorRunResult(
            status="success",
            raw={"status": "success", "total_incidents": 7, "average_response_time": 4.2},
        )


def test_full_job_pipeline(client, auth_headers, tmp_path):
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
        process_job(db, claimed, sim_factory=lambda: FakeSim(), logs_root=tmp_path)
    finally:
        db.close()

    r2 = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
    body = r2.json()
    assert body["status"] == "done"
    assert body["result"]["total_incidents"] == 7
