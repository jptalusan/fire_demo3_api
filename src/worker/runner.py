"""Fetch + lock the next pending job. SQLite-safe optimistic claim."""

from typing import Optional

from sqlalchemy.orm import Session

from db import crud
from db.models import Job


def claim_job(db: Session, worker_id: str) -> Optional[Job]:
    return crud.claim_next_pending_job(db, worker_id)
