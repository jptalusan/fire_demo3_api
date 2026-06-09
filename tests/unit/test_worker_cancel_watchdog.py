"""Mechanism test for the worker's cancellation watchdog.

Asserts the full path actually fires:

  1. A *running* sim hangs forever (no return).
  2. Another thread sets `cancel_requested=True` via crud.
  3. The watchdog (polling every 0.05s) sees the flag, cancels the work task,
     `_run_with_timeout_and_cancel` raises `_CancelledByUser`, and `process_job`
     calls `mark_job_failed` with "Cancelled by user."

If the watchdog were not wired in, the hanging sim would never be cancelled and
this test would time out. So the assertion proves the mechanism, not just "the
endpoint returns 200".
"""

import threading
import time

from db import crud
from db.session import SessionLocal
from worker.processor import process_job

from tests.unit.test_worker_processor import _HangingSim


def test_cancel_running_job_actually_stops_via_watchdog(db_session, tmp_path):
    # Create a job and pre-mark it 'running' (simulate worker having claimed it).
    user = crud.create_user(db_session, "cancel_mech", "h")
    job = crud.create_job(db_session, user_id=user.id, kind="run-simulation", payload={"config": {}})
    from db.models import Job
    db_session.query(Job).filter(Job.id == job.id).update({"status": "running"})
    db_session.commit()

    # The worker uses its own DB session (SessionLocal) inside the watchdog,
    # so run process_job in a thread to model the real architecture.
    errors: list[BaseException] = []
    worker_db = SessionLocal()

    def run():
        try:
            process_job(
                worker_db, job,
                sim_factory=lambda: _HangingSim(),
                timeout_sec=10.0,        # big — we expect the *watchdog* to fire first
                cancel_poll_sec=0.05,    # tight so the test is fast
                logs_root=tmp_path,
            )
        except BaseException as e:  # pragma: no cover - shouldn't escape
            errors.append(e)
        finally:
            worker_db.close()

    t = threading.Thread(target=run, name="worker-thread")
    started = time.monotonic()
    t.start()
    # Give the work task time to actually enter the hanging sim before we cancel.
    time.sleep(0.2)
    crud.request_cancel(db_session, job.id, user.id)

    t.join(timeout=5.0)
    elapsed = time.monotonic() - started

    assert not t.is_alive(), "watchdog never cancelled the hanging sim"
    assert errors == [], f"process_job raised: {errors}"
    # Should be well under timeout_sec — proves the watchdog (not the timeout) fired.
    assert elapsed < 3.0, f"took {elapsed:.2f}s — watchdog likely never fired"

    # The worker committed via its own session; the test's session has the row
    # cached in its identity map. Drop the cache to read the latest committed state.
    db_session.expire_all()
    refreshed = crud.get_job(db_session, job.id)
    assert refreshed.status == "failed"
    assert refreshed.error == "Cancelled by user."
    assert refreshed.cancel_requested is True
