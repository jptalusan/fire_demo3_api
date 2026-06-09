"""SQLAlchemy engine + session factory. SQLite-aware."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import settings

connect_args: dict = {}
engine_kwargs: dict = {"future": True}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    # In-memory SQLite needs StaticPool so every session sees the same DB.
    if ":memory:" in settings.DATABASE_URL:
        engine_kwargs["poolclass"] = StaticPool

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def ensure_schema_migrations() -> None:
    """Apply additive column migrations the model has added since first install.

    SQLAlchemy's `create_all` only creates missing tables; it never ALTERs an
    existing one. For a SQLite-only deployment we add the small handful of
    columns introduced after release here. Idempotent — checks PRAGMA before
    altering.
    """
    from sqlalchemy import text
    with engine.begin() as conn:
        if conn.dialect.name != "sqlite":
            return  # Postgres deployments should use a real migration tool.
        # `jobs` table may not exist yet on a brand-new install; create_all runs
        # before this is called from main.py / worker.main.
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        if "jobs" not in tables:
            return
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(jobs)"))}
        if "cancel_requested" not in cols:
            conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"
            ))


def get_db() -> Session:
    """FastAPI dependency that yields a DB session and closes it after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
