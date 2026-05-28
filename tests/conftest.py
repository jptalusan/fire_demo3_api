"""Shared pytest fixtures. Uses an in-memory SQLite DB so the file DB is never touched."""

from __future__ import annotations

import os
from typing import Iterator

import pytest

# Force in-memory SQLite + ephemeral secret BEFORE backend.config is imported.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("STORAGE_ROOT", "/tmp/fire_demo3_v2_test_storage")

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
from db.models import Base  # noqa: E402
from db.session import SessionLocal, engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Iterator[None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _truncate_tables() -> Iterator[None]:
    """Wipe every table between tests so the in-memory DB stays isolated."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db_session() -> Iterator:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_token(client) -> str:
    client.post("/auth/register", json={"username": "alice", "password": "password123"})
    resp = client.post("/auth/login", json={"username": "alice", "password": "password123"})
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}
