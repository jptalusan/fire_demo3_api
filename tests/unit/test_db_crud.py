"""Unit tests for db.crud."""

from db import crud


def test_create_and_get_user(db_session):
    crud.create_user(db_session, "bob", "hash")
    u = crud.get_user(db_session, "bob")
    assert u is not None
    assert u.username == "bob"


def test_job_lifecycle(db_session):
    user = crud.create_user(db_session, "carol", "hash")
    job = crud.create_job(db_session, user_id=user.id, kind="run-simulation", payload={"x": 1})
    assert job.status == "pending"

    claimed = crud.claim_next_pending_job(db_session, worker_id="w1")
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == "running"
    assert claimed.locked_by == "w1"

    # Second claim returns None (no pending left).
    assert crud.claim_next_pending_job(db_session, worker_id="w2") is None

    crud.mark_job_done(db_session, job.id, {"ok": True})
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "done"
    assert refreshed.result == {"ok": True}


def test_global_serialization_one_running_at_a_time(db_session):
    """A second pending job is NOT claimed while another job is running."""
    user = crud.create_user(db_session, "erin", "hash")
    j1 = crud.create_job(db_session, user_id=user.id, kind="run-simulation", payload={})
    j2 = crud.create_job(db_session, user_id=user.id, kind="run-simulation", payload={})

    first = crud.claim_next_pending_job(db_session, worker_id="w1")
    assert first.id == j1.id and first.status == "running"

    # j2 is pending, but j1 is running -> gate blocks the claim.
    assert crud.claim_next_pending_job(db_session, worker_id="w2") is None
    assert crud.get_job(db_session, j2.id).status == "pending"

    # Once j1 finishes, j2 can be claimed.
    crud.mark_job_done(db_session, j1.id, {})
    second = crud.claim_next_pending_job(db_session, worker_id="w1")
    assert second.id == j2.id and second.status == "running"


def test_reap_stale_running_unblocks_queue(db_session):
    """An orphaned running job past the grace age is failed so the queue frees up."""
    import time as _t
    user = crud.create_user(db_session, "frank", "hash")
    crud.create_job(db_session, user_id=user.id, kind="run-simulation", payload={})
    running = crud.claim_next_pending_job(db_session, worker_id="dead-worker")
    assert running.status == "running"

    # No reap with a long grace; reaped with a zero grace.
    assert crud.reap_stale_running(db_session, max_age_seconds=10_000) == 0
    _t.sleep(0.01)
    assert crud.reap_stale_running(db_session, max_age_seconds=0) == 1
    assert crud.get_job(db_session, running.id).status == "failed"


def test_mark_failed(db_session):
    user = crud.create_user(db_session, "dave", "hash")
    job = crud.create_job(db_session, user_id=user.id, kind="run-simulation", payload={})
    crud.claim_next_pending_job(db_session, worker_id="w1")
    crud.mark_job_failed(db_session, job.id, "boom")
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert refreshed.error == "boom"
