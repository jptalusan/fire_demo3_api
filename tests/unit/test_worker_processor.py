"""Unit tests for worker.processor and worker.runner with a fake Simulator.

Never invokes the real C++ simulator: default_simulator is monkeypatched to a
fake, and per-job dirs are redirected under a tmp path.
"""

import asyncio
from pathlib import Path

import pytest

import core.config as constants
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
        await asyncio.sleep(10)  # never finishes within the test timeout
        return sim_mod.SimulatorRunResult(status="success", raw={})


class _ExplodingSim(sim_mod.Simulator):
    async def run(self, req):
        raise RuntimeError("sim blew up")


@pytest.fixture
def redirect_logs(monkeypatch, tmp_path):
    """Point worker per-job log dirs at a tmp dir so we never touch real storage."""
    monkeypatch.setattr(constants, "BASE_DIR", tmp_path)
    return tmp_path


def _mkjob(db, kind, payload):
    u = crud.create_user(db, f"wp_{kind}_{id(payload)}", "h")
    return crud.create_job(db, user_id=u.id, kind=kind, payload=payload)


# ---------- _isolate_paths ----------

def test_isolate_paths_rewrites_all_write_keys(tmp_path):
    run_dir = tmp_path / "run"
    cfg = _isolate_paths({"keep": "me"}, run_dir)
    assert cfg["keep"] == "me"  # original keys preserved
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

def test_process_job_run_simulation_marks_done(db_session, monkeypatch, redirect_logs):
    fake = _FakeSim({"status": "success", "total_incidents": 5})
    monkeypatch.setattr(processor_mod, "default_simulator", lambda: fake)
    job = _mkjob(db_session, "run-simulation", {"config": {"k": "v"}})

    process_job(db_session, job)

    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "done"
    assert refreshed.result["total_incidents"] == 5
    assert "duration_seconds" in refreshed.result
    assert isinstance(refreshed.result["duration_seconds"], (int, float))


def test_process_job_uses_payload_without_config_key(db_session, monkeypatch, redirect_logs):
    """payload itself is the config when there's no 'config' subkey."""
    fake = _FakeSim({"status": "success"})
    monkeypatch.setattr(processor_mod, "default_simulator", lambda: fake)
    job = _mkjob(db_session, "run-simulation", {"some": "config"})
    process_job(db_session, job)
    assert crud.get_job(db_session, job.id).status == "done"
    # The fake saw a config containing the isolated paths.
    assert "REPORT_CSV_PATH" in fake.calls[0].config


# ---------- process_job: run-comparison ----------

def test_process_job_run_comparison_stores_all_legs(db_session, monkeypatch, redirect_logs):
    fake = _FakeSim({"status": "success", "average_response_time": 4.0, "coverage_percent": 90.0, "P90_continuous": 8.0})
    monkeypatch.setattr(processor_mod, "default_simulator", lambda: fake)
    job = _mkjob(db_session, "run-comparison", {"baseline": {"a": 1}, "newConfig": {"b": 2}})

    process_job(db_session, job)

    result = crud.get_job(db_session, job.id).result
    assert result["status"] == "success"
    assert "baseline" in result and "newConfig" in result
    assert "comparison" in result
    assert "overall_metrics" in result["comparison"]
    # Both legs were run.
    assert len(fake.calls) == 2


def test_process_job_marks_failed_when_sim_returns_error_status(db_session, monkeypatch, redirect_logs):
    """A simulator returning {"status":"error", ...} must fail the job, not silently mark it done.

    Regression for a real bug found during a fresh-clone setup walk: a missing
    data file made the engine return an error dict, the worker called
    mark_job_done unconditionally, and the user saw a "successful" job with no
    real result. The worker now inspects the result and fails the job.
    """
    fake = _FakeSim({"status": "error", "error": "boom"})
    monkeypatch.setattr(processor_mod, "default_simulator", lambda: fake)
    job = _mkjob(db_session, "run-comparison", {"baseline": {}, "newConfig": {}})
    process_job(db_session, job)
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert "boom" in (refreshed.error or "")


# ---------- process_job: error paths ----------

def test_process_job_unknown_kind_fails(db_session, monkeypatch, redirect_logs):
    monkeypatch.setattr(processor_mod, "default_simulator", lambda: _FakeSim({"status": "success"}))
    job = _mkjob(db_session, "bogus-kind", {})
    process_job(db_session, job)
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert "Unknown job kind" in refreshed.error


def test_process_job_sim_exception_marks_failed(db_session, monkeypatch, redirect_logs):
    monkeypatch.setattr(processor_mod, "default_simulator", lambda: _ExplodingSim())
    job = _mkjob(db_session, "run-simulation", {"config": {}})
    process_job(db_session, job)
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert "sim blew up" in refreshed.error


def test_process_job_timeout_marks_failed(db_session, monkeypatch, redirect_logs):
    """A hanging sim is cancelled at JOB_TIMEOUT_SEC and the job fails fast."""
    monkeypatch.setattr(processor_mod, "JOB_TIMEOUT_SEC", 0.2)
    monkeypatch.setattr(processor_mod, "default_simulator", lambda: _HangingSim())
    job = _mkjob(db_session, "run-simulation", {"config": {}})
    process_job(db_session, job)
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert "limit and was cancelled" in refreshed.error


# ---------- runner.claim_job ----------

def test_runner_claim_job_delegates_to_crud(db_session, monkeypatch):
    sentinel = object()
    captured = {}

    def fake_claim(db, worker_id):
        captured["args"] = (db, worker_id)
        return sentinel

    monkeypatch.setattr(runner_mod.crud, "claim_next_pending_job", fake_claim)
    out = runner_mod.claim_job(db_session, "worker-x")
    assert out is sentinel
    assert captured["args"] == (db_session, "worker-x")
