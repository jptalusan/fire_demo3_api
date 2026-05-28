"""Unit tests for the jobs progress helpers (_leg_progress, _job_progress)."""

import json
from types import SimpleNamespace

from backend.routes import jobs as jobs_mod
from backend.routes.jobs import _job_progress, _leg_progress


def _write_leg(leg_dir, total=None, processed_lines=0, noise_lines=0):
    leg_dir.mkdir(parents=True, exist_ok=True)
    if total is not None:
        (leg_dir / "progress.json").write_text(json.dumps({"total": total}))
    lines = [f"incident {i} is reported\n" for i in range(processed_lines)]
    lines += ["unrelated log line\n" for _ in range(noise_lines)]
    if lines:
        (leg_dir / "sim.log").write_text("".join(lines))


def test_leg_progress_counts_reported_markers(tmp_path):
    _write_leg(tmp_path, total=10, processed_lines=3, noise_lines=5)
    assert _leg_progress(tmp_path) == {"processed": 3, "total": 10}


def test_leg_progress_missing_files(tmp_path):
    assert _leg_progress(tmp_path / "nope") == {"processed": 0, "total": 0}


def test_leg_progress_clamps_to_total(tmp_path):
    _write_leg(tmp_path, total=2, processed_lines=9)
    assert _leg_progress(tmp_path) == {"processed": 2, "total": 2}


def test_leg_progress_bad_progress_json(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "progress.json").write_text("{not json")
    _write_leg(tmp_path, total=None, processed_lines=4)
    res = _leg_progress(tmp_path)
    assert res["total"] == 0
    # With total==0 there's no clamp, so processed reflects the raw count.
    assert res["processed"] == 4


def test_job_progress_single_leg(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_mod, "JOBS_LOG_ROOT", tmp_path)
    job = SimpleNamespace(id=1, status="running", kind="run-simulation")
    _write_leg(tmp_path / "job_1", total=4, processed_lines=2)
    out = _job_progress(job)
    assert out["job_id"] == 1
    assert out["processed"] == 2 and out["total"] == 4
    assert out["percent"] == 50.0
    assert set(out["legs"]) == {"simulation"}


def test_job_progress_comparison_two_legs(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_mod, "JOBS_LOG_ROOT", tmp_path)
    job = SimpleNamespace(id=2, status="running", kind="run-comparison")
    base = tmp_path / "job_2"
    _write_leg(base / "baseline", total=4, processed_lines=1)
    _write_leg(base / "newconfig", total=6, processed_lines=3)
    out = _job_progress(job)
    assert set(out["legs"]) == {"baseline", "newConfig"}
    assert out["processed"] == 4 and out["total"] == 10
    assert out["percent"] == 40.0


def test_job_progress_zero_total_percent_is_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_mod, "JOBS_LOG_ROOT", tmp_path)
    job = SimpleNamespace(id=3, status="pending", kind="run-simulation")
    out = _job_progress(job)
    assert out["total"] == 0
    assert out["percent"] == 0.0
