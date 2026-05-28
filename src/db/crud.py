"""CRUD operations for User and Job."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from db.models import Job, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- User ----------

def create_user(db: Session, username: str, password_hash: str) -> User:
    user = User(username=username, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter_by(username=username).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter_by(id=user_id).first()


# ---------- Job ----------

def create_job(db: Session, user_id: int, kind: str, payload: dict, priority: int = 0) -> Job:
    job = Job(user_id=user_id, kind=kind, payload=payload, priority=priority, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: int) -> Optional[Job]:
    return db.query(Job).filter_by(id=job_id).first()


def list_jobs(db: Session, user_id: int) -> list[Job]:
    return (
        db.query(Job)
        .filter_by(user_id=user_id)
        .order_by(Job.created_at.desc())
        .all()
    )


def claim_next_pending_job(db: Session, worker_id: str) -> Optional[Job]:
    """Claim the next pending job — but only if nothing is already running.

    Enforces **global serialization**: at most one job runs at a time across the
    whole system, no matter how many workers poll or which users submitted. A new
    request always queues behind an in-flight one rather than running concurrently.

    Returns the claimed Job (now 'running'), or None if nothing to do or another
    job is already running.
    """
    # Global gate: if any job is currently running, do not start another.
    if db.query(Job).filter(Job.status == "running").count() > 0:
        return None

    candidate = (
        db.query(Job)
        .filter(Job.status == "pending")
        .order_by(Job.priority.desc(), Job.created_at.asc())
        .first()
    )
    if candidate is None:
        return None
    rows = (
        db.query(Job)
        .filter(Job.id == candidate.id, Job.status == "pending")
        .update(
            {
                "status": "running",
                "started_at": _utcnow(),
                "locked_by": worker_id,
                "attempts": Job.attempts + 1,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if rows == 0:
        # Another worker claimed this exact job first; try again next tick.
        return None

    # Defensive de-race: if two workers both passed the gate and each claimed a
    # *different* pending job, more than one would now be running. Detect that and
    # yield the one we just took back to the queue, keeping the oldest runner.
    running = (
        db.query(Job)
        .filter(Job.status == "running")
        .order_by(Job.started_at.asc())
        .all()
    )
    if len(running) > 1 and running[0].id != candidate.id:
        db.query(Job).filter(Job.id == candidate.id).update(
            {"status": "pending", "started_at": None, "locked_by": None,
             "attempts": Job.attempts - 1},
            synchronize_session=False,
        )
        db.commit()
        return None

    db.refresh(candidate)
    return candidate


def reap_stale_running(db: Session, max_age_seconds: float) -> int:
    """Fail any 'running' job older than max_age_seconds.

    Because the queue is globally serialized (only one job runs at a time), a job
    orphaned by a crashed worker would otherwise block ALL future jobs forever.
    A live job can't exceed the worker's own timeout, so anything older than that
    is dead — mark it failed to unblock the queue.

    Returns the number of jobs reaped.
    """
    from datetime import timedelta

    cutoff = _utcnow().replace(tzinfo=None) - timedelta(seconds=max_age_seconds)
    rows = (
        db.query(Job)
        .filter(Job.status == "running", Job.started_at < cutoff)
        .update(
            {
                "status": "failed",
                "error": "Orphaned: no live worker (exceeded max run age); reaped to unblock the queue.",
                "finished_at": _utcnow().replace(tzinfo=None),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return rows


def mark_job_done(db: Session, job_id: int, result: Any) -> None:
    db.query(Job).filter(Job.id == job_id).update(
        {"status": "done", "result": result, "finished_at": _utcnow()},
        synchronize_session=False,
    )
    db.commit()


def mark_job_failed(db: Session, job_id: int, error: str) -> None:
    db.query(Job).filter(Job.id == job_id).update(
        {"status": "failed", "error": error, "finished_at": _utcnow()},
        synchronize_session=False,
    )
    db.commit()


# ---------- Queue introspection ----------

def _pending_queue_ids(db: Session) -> list[int]:
    """All pending job ids in worker-dispatch order (priority desc, oldest first)."""
    rows = (
        db.query(Job.id)
        .filter(Job.status == "pending")
        .order_by(Job.priority.desc(), Job.created_at.asc())
        .all()
    )
    return [r[0] for r in rows]


def queue_position(db: Session, job_id: int) -> Optional[int]:
    """1-based position of a pending job in the global queue, else None."""
    ids = _pending_queue_ids(db)
    return ids.index(job_id) + 1 if job_id in ids else None


def queue_status(db: Session, user_id: int) -> dict:
    """Counts across all users + this user's standing and next queue position."""
    ids = _pending_queue_ids(db)
    pending_total = len(ids)
    running_total = db.query(Job).filter(Job.status == "running").count()
    your_pending = db.query(Job).filter(Job.status == "pending", Job.user_id == user_id).count()
    your_running = db.query(Job).filter(Job.status == "running", Job.user_id == user_id).count()

    your_next_position: Optional[int] = None
    for pos, jid in enumerate(ids, start=1):
        owner = db.query(Job.user_id).filter(Job.id == jid).scalar()
        if owner == user_id:
            your_next_position = pos
            break

    return {
        "pending_total": pending_total,
        "running_total": running_total,
        "your_pending": your_pending,
        "your_running": your_running,
        "your_next_position": your_next_position,
    }
