"""Unit tests for worker.processor and worker.runner.

No monkey-patching: the Simulator, timeout, watchdog cadence, and logs root are
all injected into `process_job` so each test wires its own fakes.
"""

import asyncio

import pytest

from backend.services import simulator as sim_mod
from db import crud
from worker import processor as processor_mod
from worker import runner as runner_mod
from worker.processor import _isolate_paths, process_job


# ---------- fakes ----------

class _FakeSim(sim_mod.Simulator):
    def __init__(self, raw):
        self.raw = raw
        self.calls = []

    async def run(self, req):
        self.calls.append(req)
        return sim_mod.SimulatorRunResult(status=self.raw.get("status", "error"), raw=self.raw)


class _HangingSim(sim_mod.Simulator):
    async def run(self, req):
        await asyncio.sleep(60)  # never finishes within the test timeout
        return sim_mod.SimulatorRunResult(status="success", raw={})


class _ExplodingSim(sim_mod.Simulator):
    async def run(self, req):
        raise RuntimeError("sim blew up")


def _mkjob(db, kind, payload):
    u = crud.create_user(db, f"wp_{kind}_{id(payload)}", "h")
    return crud.create_job(db, user_id=u.id, kind=kind, payload=payload)


# ---------- _isolate_paths ----------

def test_isolate_paths_rewrites_all_write_keys(tmp_path):
    run_dir = tmp_path / "run"
    cfg = _isolate_paths({"keep": "me"}, run_dir)
    assert cfg["keep"] == "me"
    for key in (
        "REPORT_CSV_PATH", "STATION_REPORT_CSV_PATH", "EMS_TRANSPORT_REPORT_PATH",
        "DURATION_MATRIX_PATH", "DISTANCE_MATRIX_PATH", "MATRIX_CSV_PATH",
        "FIREBEATS_MATRIX_PATH",
    ):
        assert cfg[key].startswith(str(run_dir))
    assert run_dir.exists()


def test_isolate_paths_is_idempotent(tmp_path):
    run_dir = tmp_path / "run"
    a = _isolate_paths({}, run_dir)
    b = _isolate_paths(a, run_dir)
    assert a["REPORT_CSV_PATH"] == b["REPORT_CSV_PATH"]


def test_isolate_paths_does_not_mutate_input(tmp_path):
    original = {"x": 1}
    _isolate_paths(original, tmp_path / "r")
    assert original == {"x": 1}


# ---------- process_job: run-simulation ----------

def test_process_job_run_simulation_marks_done(db_session, tmp_path):
    fake = _FakeSim({"status": "success", "total_incidents": 5})
    job = _mkjob(db_session, "run-simulation", {"config": {"k": "v"}})

    process_job(db_session, job, sim_factory=lambda: fake, logs_root=tmp_path)

    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "done"
    assert refreshed.result["total_incidents"] == 5
    assert isinstance(refreshed.result.get("duration_seconds"), (int, float))


def test_process_job_uses_payload_without_config_key(db_session, tmp_path):
    """payload itself is the config when there's no 'config' subkey."""
    fake = _FakeSim({"status": "success"})
    job = _mkjob(db_session, "run-simulation", {"some": "config"})
    process_job(db_session, job, sim_factory=lambda: fake, logs_root=tmp_path)
    assert crud.get_job(db_session, job.id).status == "done"
    assert "REPORT_CSV_PATH" in fake.calls[0].config


# ---------- process_job: run-comparison ----------

def test_process_job_run_comparison_stores_all_legs(db_session, tmp_path):
    fake = _FakeSim({"status": "success", "average_response_time": 4.0, "coverage_percent": 90.0, "P90_continuous": 8.0})
    job = _mkjob(db_session, "run-comparison", {"baseline": {"a": 1}, "newConfig": {"b": 2}})

    process_job(db_session, job, sim_factory=lambda: fake, logs_root=tmp_path)

    result = crud.get_job(db_session, job.id).result
    assert result["status"] == "success"
    assert "baseline" in result and "newConfig" in result
    assert "comparison" in result and "overall_metrics" in result["comparison"]
    assert len(fake.calls) == 2  # both legs ran


def test_process_job_marks_failed_when_sim_returns_error_status(db_session, tmp_path):
    """A simulator returning {"status":"error", ...} must fail the job, not silently mark it done.

    Regression test: previously the worker called mark_job_done unconditionally,
    so a missing data file surfaced as a "successful" job with no result.
    """
    fake = _FakeSim({"status": "error", "error": "boom"})
    job = _mkjob(db_session, "run-comparison", {"baseline": {}, "newConfig": {}})
    process_job(db_session, job, sim_factory=lambda: fake, logs_root=tmp_path)
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert "boom" in (refreshed.error or "")


# ---------- process_job: error paths ----------

def test_process_job_unknown_kind_fails(db_session, tmp_path):
    job = _mkjob(db_session, "bogus-kind", {})
    process_job(db_session, job, sim_factory=lambda: _FakeSim({"status": "success"}), logs_root=tmp_path)
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert "Unknown job kind" in refreshed.error


def test_process_job_sim_exception_marks_failed(db_session, tmp_path):
    job = _mkjob(db_session, "run-simulation", {"config": {}})
    process_job(db_session, job, sim_factory=lambda: _ExplodingSim(), logs_root=tmp_path)
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert "sim blew up" in refreshed.error


def test_process_job_timeout_marks_failed(db_session, tmp_path):
    """A hanging sim is cancelled at `timeout_sec` and the job fails fast."""
    job = _mkjob(db_session, "run-simulation", {"config": {}})
    process_job(
        db_session, job,
        sim_factory=lambda: _HangingSim(),
        timeout_sec=0.2,
        cancel_poll_sec=5.0,   # large so the timeout, not the watchdog, fires
        logs_root=tmp_path,
    )
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert "limit and was cancelled" in refreshed.error


# ---------- runner.claim_job ----------

def test_runner_claim_job_delegates_to_crud(db_session):
    out = runner_mod.claim_job(db_session, "worker-x")
    # No pending jobs -> None is the contract.
    assert out is None
