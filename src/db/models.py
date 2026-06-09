"""SQLAlchemy ORM models for users and jobs."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # pending | running | done | failed
    status = Column(String, default="pending", index=True)
    # Job kind so worker can route to right handler: run-simulation | run-comparison
    kind = Column(String, default="run-simulation")
    payload = Column(JSON)
    result = Column(JSON)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    priority = Column(Integer, default=0)
    locked_by = Column(String, nullable=True)
    # User can request cancellation at any point. Worker watchdog polls this and
    # cancels the in-flight task; for pending jobs the route flips status directly.
    cancel_requested = Column(Boolean, nullable=False, default=False, server_default="0")
