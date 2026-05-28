"""Unit tests for backend.schemas.sim models and the jobs._duration_seconds helper."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.routes.jobs import _duration_seconds
from backend.schemas.sim import (
    JobProgress,
    JobResponse,
    JobSubmitRequest,
    QueueStatus,
)


# ---------- JobSubmitRequest ----------

def test_job_submit_defaults():
    req = JobSubmitRequest(payload={"a": 1})
    assert req.kind == "run-simulation"
    assert req.priority == 0
    assert req.payload == {"a": 1}


def test_job_submit_comparison_kind():
    req = JobSubmitRequest(kind="run-comparison", payload={"baseline": {}, "newConfig": {}}, priority=3)
    assert req.kind == "run-comparison"
    assert req.priority == 3


def test_job_submit_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        JobSubmitRequest(kind="explode", payload={})


def test_job_submit_payload_required():
    with pytest.raises(ValidationError):
        JobSubmitRequest()  # payload has no default


# ---------- JobResponse / JobProgress / QueueStatus construct ----------

def test_job_response_constructs():
    jr = JobResponse(
        id=1, user_id=2, kind="run-simulation", status="pending",
        payload={"x": 1}, result=None, error=None, attempts=0,
    )
    assert jr.id == 1
    assert jr.duration_seconds is None
    assert jr.queue_position is None


def test_job_progress_constructs():
    jp = JobProgress(job_id=1, status="running", processed=2, total=10, percent=20.0, legs={"simulation": {"processed": 2, "total": 10}})
    assert jp.percent == 20.0


def test_queue_status_constructs():
    qs = QueueStatus(pending_total=1, running_total=0, your_pending=1, your_running=0, your_next_position=1)
    assert qs.your_next_position == 1
    qs2 = QueueStatus(pending_total=0, running_total=0, your_pending=0, your_running=0)
    assert qs2.your_next_position is None


# ---------- _duration_seconds tz-safety regression ----------

def test_duration_both_naive():
    job = SimpleNamespace(
        started_at=datetime(2024, 1, 1, 0, 0, 0),
        finished_at=datetime(2024, 1, 1, 0, 0, 5),
    )
    assert _duration_seconds(job) == 5.0


def test_duration_both_aware():
    job = SimpleNamespace(
        started_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=3),
    )
    assert _duration_seconds(job) == 3.0


def test_duration_mixed_naive_and_aware_does_not_raise():
    """Regression: a mix of naive + aware timestamps must not raise."""
    job = SimpleNamespace(
        started_at=datetime(2024, 1, 1, 0, 0, 0),  # naive
        finished_at=datetime(2024, 1, 1, 0, 0, 10, tzinfo=timezone.utc),  # aware
    )
    # Must not raise "can't subtract offset-naive and offset-aware".
    assert _duration_seconds(job) == 10.0

    job2 = SimpleNamespace(
        started_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),  # aware
        finished_at=datetime(2024, 1, 1, 0, 0, 4),  # naive
    )
    assert _duration_seconds(job2) == 4.0


def test_duration_none_when_unfinished():
    assert _duration_seconds(SimpleNamespace(started_at=datetime.now(), finished_at=None)) is None
    assert _duration_seconds(SimpleNamespace(started_at=None, finished_at=datetime.now())) is None
