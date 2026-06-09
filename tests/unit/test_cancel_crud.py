"""Unit tests for the cancellation CRUD: every outcome is exercised.

The behavior is mechanism-asserting:
  - pending job is flipped to failed *with a specific error message*.
  - running job has the flag set; status remains 'running' until a worker acts.
  - terminal jobs are NOT mutated (idempotent no-op surfaced as a distinct token).
"""

import pytest

from db import crud


def _mk(db, username, status):
    user = crud.create_user(db, username, "h")
    job = crud.create_job(db, user_id=user.id, kind="run-simulation", payload={})
    if status != "pending":
        # Drive the row into the requested status using ORM (no SQL hacks).
        from db.models import Job
        db.query(Job).filter(Job.id == job.id).update({"status": status})
        db.commit()
    return user, job


def test_request_cancel_pending_flips_to_failed_with_message(db_session):
    user, job = _mk(db_session, "u1", "pending")
    outcome = crud.request_cancel(db_session, job.id, user.id)
    assert outcome == "cancelled_pending"
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert refreshed.cancel_requested is True
    assert "Cancelled by user before it started." in (refreshed.error or "")
    assert refreshed.finished_at is not None


def test_request_cancel_running_sets_flag_but_does_not_kill(db_session):
    user, job = _mk(db_session, "u2", "running")
    outcome = crud.request_cancel(db_session, job.id, user.id)
    assert outcome == "cancel_requested"
    refreshed = crud.get_job(db_session, job.id)
    # Still running — only the watchdog (worker) can transition it.
    assert refreshed.status == "running"
    assert refreshed.cancel_requested is True
    assert refreshed.error is None
    assert refreshed.finished_at is None


def test_request_cancel_done_is_noop(db_session):
    user, job = _mk(db_session, "u3", "done")
    outcome = crud.request_cancel(db_session, job.id, user.id)
    assert outcome == "already_terminal"
    refreshed = crud.get_job(db_session, job.id)
    # NOTHING changed.
    assert refreshed.status == "done"
    assert refreshed.cancel_requested is False
    assert refreshed.error is None


def test_request_cancel_failed_is_noop(db_session):
    user, job = _mk(db_session, "u4", "failed")
    outcome = crud.request_cancel(db_session, job.id, user.id)
    assert outcome == "already_terminal"


def test_request_cancel_other_user_returns_not_found(db_session):
    owner, job = _mk(db_session, "owner", "pending")
    stranger = crud.create_user(db_session, "stranger", "h")
    outcome = crud.request_cancel(db_session, job.id, stranger.id)
    assert outcome == "not_found"
    # Owner's job untouched.
    assert crud.get_job(db_session, job.id).status == "pending"


def test_is_cancel_requested_reads_flag(db_session):
    user, job = _mk(db_session, "u5", "running")
    assert crud.is_cancel_requested(db_session, job.id) is False
    crud.request_cancel(db_session, job.id, user.id)
    assert crud.is_cancel_requested(db_session, job.id) is True


def test_is_cancel_requested_raises_on_missing_row(db_session):
    # No silent fallback: a missing row must surface, not return False.
    with pytest.raises(LookupError):
        crud.is_cancel_requested(db_session, 999_999)
