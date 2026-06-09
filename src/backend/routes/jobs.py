"""Job-queue endpoints (queued simulation runs)."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import core.config as constants
from backend.schemas.sim import JobProgress, JobResponse, JobSubmitRequest, QueueStatus
from backend.services.auth import get_current_user
from db import crud
from db.session import get_db

router = APIRouter()

# Per-job working dir written by the worker (see worker/processor.py).
JOBS_LOG_ROOT = constants.BASE_DIR / "logs"

# A simulator logs one of these per incident as it enters the run.
_PROCESSED_MARKER = "is reported"


def _leg_progress(leg_dir: Path) -> dict:
    """Read a single simulation leg's progress from its sim.log + progress.json."""
    total = 0
    pj = leg_dir / "progress.json"
    if pj.exists():
        try:
            total = int(json.loads(pj.read_text()).get("total", 0))
        except Exception:
            total = 0
    processed = 0
    log = leg_dir / "sim.log"
    if log.exists():
        try:
            with open(log, "r", errors="ignore") as f:
                processed = sum(1 for line in f if _PROCESSED_MARKER in line)
        except Exception:
            processed = 0
    # Don't let a noisy log report more than the known total.
    if total:
        processed = min(processed, total)
    return {"processed": processed, "total": total}


def _job_progress(job) -> dict:
    """Aggregate progress across a job's legs (1 for run-simulation, 2 for comparison)."""
    base = JOBS_LOG_ROOT / f"job_{job.id}"
    if job.kind == "run-comparison":
        legs = {"baseline": _leg_progress(base / "baseline"), "newConfig": _leg_progress(base / "newconfig")}
    else:
        legs = {"simulation": _leg_progress(base)}
    processed = sum(l["processed"] for l in legs.values())
    total = sum(l["total"] for l in legs.values())
    percent = round(100.0 * processed / total, 1) if total else 0.0
    return {
        "job_id": job.id,
        "status": job.status,
        "processed": processed,
        "total": total,
        "percent": percent,
        "legs": legs,
    }


def _duration_seconds(job) -> Optional[float]:
    if job.started_at and job.finished_at:
        # SQLite has no tz type: ORM-written timestamps read back naive, but a
        # manual update can land an aware value. Drop tzinfo on both so a mixed
        # pair can't raise "can't subtract offset-naive and offset-aware".
        start = job.started_at.replace(tzinfo=None)
        finish = job.finished_at.replace(tzinfo=None)
        return round((finish - start).total_seconds(), 2)
    return None


def _serialize(job, queue_position: Optional[int] = None) -> JobResponse:
    return JobResponse(
        id=job.id,
        user_id=job.user_id,
        kind=job.kind,
        status=job.status,
        payload=job.payload,
        result=job.result,
        error=job.error,
        attempts=job.attempts or 0,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        duration_seconds=_duration_seconds(job),
        queue_position=queue_position,
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def submit(
    body: JobSubmitRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a simulation job to the queue.

    Returns immediately with a job in `pending` status — a background worker picks
    it up. Poll `GET /api/jobs/{id}` until `status` is `done` or `failed`, and
    `GET /api/jobs/{id}/progress` for live incident progress.

    Payload by kind:
    - **run-simulation** — `payload` is a SimConfig (models, date_range,
      incident_type, dispatch_policy, station_data, optional custom stations).
    - **run-comparison** — `payload` is `{baseline: SimConfig, newConfig: SimConfig}`;
      both run in parallel and the result includes a per-metric diff.

    See the request examples for full bodies. Note: a config that can't resolve
    its incidents (e.g. fire incidents with no Engine apparatus) will run until
    the per-job timeout and then fail.
    """
    job = crud.create_job(db, user_id=user_id, kind=body.kind, payload=body.payload, priority=body.priority)
    return _serialize(job, queue_position=crud.queue_position(db, job.id))


@router.get("", response_model=list[JobResponse])
def list_all(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    compact: bool = Query(
        False,
        description="If true, omit `payload` and `result` (sets them to null). "
        "Useful for history lists where you don't want to load tens of KB per row.",
    ),
):
    """List the authenticated user's jobs, newest first.

    Each row carries its config (`payload`), `result` once done,
    `duration_seconds`, and timestamps. Pass `?compact=true` to drop the
    `payload` and `result` blobs.
    """
    jobs = crud.list_jobs(db, user_id=user_id)
    positions = {jid: i + 1 for i, jid in enumerate(crud._pending_queue_ids(db))}
    out = [_serialize(j, queue_position=positions.get(j.id)) for j in jobs]
    if compact:
        for r in out:
            r.payload = None
            r.result = None
    return out


# Declared before /{job_id} so "queue" isn't captured as a job id.
@router.get("/queue/status", response_model=QueueStatus)
def queue_status(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    """Queue snapshot: pending/running counts across all users, your counts, and
    your earliest job's 1-based position in the global queue."""
    return QueueStatus(**crud.queue_status(db, user_id))


@router.post("/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel(
    job_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Cancel a pending or running job owned by the caller.

    Outcomes (returned in `result`):

    - `cancelled_pending` — job was pending; status flipped to `failed` immediately.
    - `cancel_requested` — job was running; the worker's watchdog will stop it
      within a few seconds.
    - `already_terminal` — job is already `done` or `failed`; nothing to do (returns 200).

    Returns 404 if the job doesn't exist or isn't yours.
    """
    outcome = crud.request_cancel(db, job_id=job_id, user_id=user_id)
    if outcome == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    job = crud.get_job(db, job_id)
    return {
        "result": outcome,
        "job": _serialize(job, queue_position=crud.queue_position(db, job.id)).model_dump(),
    }


@router.get("/{job_id}/progress", response_model=JobProgress)
def progress(
    job_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Live progress for a job: incidents processed / total and percent, derived
    from the simulator log. For comparisons, `legs` breaks it down per side.

    Note: progress tracks incidents *reported* (which fills early); the `status`
    field remains the source of truth for completion.
    """
    job = crud.get_job(db, job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_progress(job)


@router.get("/{job_id}", response_model=JobResponse)
def get_one(
    job_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch one job by id (must belong to the caller). `result` holds the full
    simulation output once `status='done'`; `error` explains a `failed` job."""
    job = crud.get_job(db, job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _serialize(job, queue_position=crud.queue_position(db, job.id))
