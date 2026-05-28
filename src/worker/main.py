"""Worker entrypoint. Polls DB for pending jobs and processes them."""

import logging
import os
import socket
import time

from sqlalchemy import text

from db import crud
from db.models import Base
from db.session import SessionLocal, engine
from worker.runner import claim_job
from worker.processor import JOB_TIMEOUT_SEC, process_job

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"
POLL_INTERVAL_SEC = float(os.getenv("WORKER_POLL_INTERVAL", "1.0"))
# A running job older than this is considered orphaned (a live one can't exceed
# its own timeout). Job timeout + 60s grace.
RUNNING_GRACE_SEC = JOB_TIMEOUT_SEC + 60


def wait_for_database(retries: int = 60, delay: float = 1.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:
            logger.warning(f"Database not ready ({attempt}/{retries}): {exc}")
            time.sleep(delay)
    raise RuntimeError("Database did not become ready in time")


def run_worker() -> None:
    logger.info(f"Worker {WORKER_ID} starting.")
    wait_for_database()
    Base.metadata.create_all(bind=engine)

    while True:
        db = SessionLocal()
        try:
            # Unblock the (globally serialized) queue if a crashed worker left a
            # job stuck 'running'. Grace = job timeout + 60s so we never reap a
            # job a live worker is legitimately still running.
            reaped = crud.reap_stale_running(db, RUNNING_GRACE_SEC)
            if reaped:
                logger.warning(f"Reaped {reaped} stale running job(s).")

            job = claim_job(db, WORKER_ID)
            if job is None:
                time.sleep(POLL_INTERVAL_SEC)
                continue
            logger.info(f"Processing job {job.id} kind={job.kind}")
            process_job(db, job)
        except Exception as exc:  # never let the loop die
            logger.exception(f"Worker tick failed: {exc}")
            time.sleep(POLL_INTERVAL_SEC)
        finally:
            db.close()


if __name__ == "__main__":
    run_worker()
