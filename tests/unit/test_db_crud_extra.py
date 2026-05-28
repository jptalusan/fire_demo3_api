"""Extra unit tests for db.crud: queue introspection, ordering, reaping edge cases."""

import time as _t
from datetime import timedelta

from db import crud
from db.models import Job


def _mkuser(db, name="u"):
    return crud.create_user(db, name, "hash")


# ---------- users ----------

def test_get_user_by_id_and_missing(db_session):
    u = _mkuser(db_session, "ida")
    assert crud.get_user_by_id(db_session, u.id).username == "ida"
    assert crud.get_user_by_id(db_session, 999999) is None
    assert crud.get_user(db_session, "nobody") is None


# ---------- list ordering ----------

def test_list_jobs_newest_first_and_scoped_to_user(db_session):
    u1 = _mkuser(db_session, "j1")
    u2 = _mkuser(db_session, "j2")
    a = crud.create_job(db_session, user_id=u1.id, kind="run-simulation", payload={})
    _t.sleep(0.01)
    b = crud.create_job(db_session, user_id=u1.id, kind="run-simulation", payload={})
    crud.create_job(db_session, user_id=u2.id, kind="run-simulation", payload={})

    jobs = crud.list_jobs(db_session, user_id=u1.id)
    assert [j.id for j in jobs] == [b.id, a.id]  # newest first
    assert all(j.user_id == u1.id for j in jobs)  # scoped


# ---------- claim ordering: priority desc, then oldest first ----------

def test_claim_respects_priority_then_age(db_session):
    u = _mkuser(db_session, "prio")
    low_old = crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={}, priority=0)
    _t.sleep(0.01)
    high_new = crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={}, priority=5)
    _t.sleep(0.01)
    high_old_ish = crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={}, priority=5)

    # Highest priority wins; among equal priority, the older one is claimed first.
    claimed = crud.claim_next_pending_job(db_session, worker_id="w")
    assert claimed.id == high_new.id
    assert low_old.id != claimed.id and high_old_ish.id != claimed.id


def test_pending_queue_ids_order(db_session):
    u = _mkuser(db_session, "qids")
    j_lo = crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={}, priority=0)
    _t.sleep(0.01)
    j_hi = crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={}, priority=9)
    ids = crud._pending_queue_ids(db_session)
    assert ids == [j_hi.id, j_lo.id]


def test_claim_returns_none_when_empty(db_session):
    assert crud.claim_next_pending_job(db_session, worker_id="w") is None


# ---------- serialization gate with a pre-existing runner ----------

def test_gate_blocks_when_a_runner_already_exists(db_session):
    """If a job is already 'running' (e.g. claimed by another worker), the gate
    blocks any further claim regardless of pending jobs present."""
    u = _mkuser(db_session, "race")
    older = crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={})
    db_session.query(Job).filter(Job.id == older.id).update(
        {"status": "running", "started_at": crud._utcnow().replace(tzinfo=None) - timedelta(seconds=5)},
        synchronize_session=False,
    )
    db_session.commit()
    pending = crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={})
    assert crud.claim_next_pending_job(db_session, worker_id="w2") is None
    assert crud.get_job(db_session, pending.id).status == "pending"


# ---------- reap edge cases ----------

def test_reap_leaves_fresh_running(db_session):
    u = _mkuser(db_session, "fresh")
    crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={})
    running = crud.claim_next_pending_job(db_session, worker_id="w")
    assert running.status == "running"
    # Large grace -> not reaped.
    assert crud.reap_stale_running(db_session, max_age_seconds=10_000) == 0
    assert crud.get_job(db_session, running.id).status == "running"


def test_reap_unblocks_queue(db_session):
    u = _mkuser(db_session, "unblock")
    crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={})
    next_job = crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={})
    stale = crud.claim_next_pending_job(db_session, worker_id="dead")
    _t.sleep(0.01)
    # Reap the stale runner; queue should now be claimable.
    assert crud.reap_stale_running(db_session, max_age_seconds=0) >= 1
    claimed = crud.claim_next_pending_job(db_session, worker_id="live")
    assert claimed is not None
    assert claimed.id == next_job.id
    assert crud.get_job(db_session, stale.id).status == "failed"


def test_reap_no_running_returns_zero(db_session):
    assert crud.reap_stale_running(db_session, max_age_seconds=0) == 0


# ---------- queue_position / queue_status ----------

def test_queue_position_none_for_non_pending(db_session):
    u = _mkuser(db_session, "qp")
    j = crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={})
    assert crud.queue_position(db_session, j.id) == 1
    crud.claim_next_pending_job(db_session, worker_id="w")
    assert crud.queue_position(db_session, j.id) is None  # now running, not pending
    assert crud.queue_position(db_session, 999999) is None


def test_queue_status_counts_and_next_position(db_session):
    u1 = _mkuser(db_session, "qs1")
    u2 = _mkuser(db_session, "qs2")
    # u2 submits first (older), u1 second.
    other = crud.create_job(db_session, user_id=u2.id, kind="run-simulation", payload={})
    _t.sleep(0.01)
    mine = crud.create_job(db_session, user_id=u1.id, kind="run-simulation", payload={})

    st = crud.queue_status(db_session, user_id=u1.id)
    assert st["pending_total"] == 2
    assert st["running_total"] == 0
    assert st["your_pending"] == 1
    assert st["your_running"] == 0
    # u2's job is older, so u1's earliest pending is at position 2.
    assert st["your_next_position"] == 2


def test_queue_status_no_jobs_for_user(db_session):
    u = _mkuser(db_session, "empty")
    st = crud.queue_status(db_session, user_id=u.id)
    assert st == {
        "pending_total": 0,
        "running_total": 0,
        "your_pending": 0,
        "your_running": 0,
        "your_next_position": None,
    }


def test_queue_status_running_counts(db_session):
    u = _mkuser(db_session, "runcount")
    crud.create_job(db_session, user_id=u.id, kind="run-simulation", payload={})
    crud.claim_next_pending_job(db_session, worker_id="w")
    st = crud.queue_status(db_session, user_id=u.id)
    assert st["running_total"] == 1
    assert st["your_running"] == 1
    assert st["your_next_position"] is None
