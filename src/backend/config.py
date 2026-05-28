"""Application settings loaded from environment / .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


class Settings:
    DATABASE_URL: str
    SECRET_KEY: str
    MAX_ATTEMPTS: int
    STORAGE_ROOT: str
    OSRM_HOST: str
    OSRM_PORT: int
    SIMULATOR_BINARY: str


settings = Settings()
settings.DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{REPO_ROOT}/storage/app.db")
settings.SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
settings.MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "5"))
settings.STORAGE_ROOT = os.getenv("STORAGE_ROOT", str(REPO_ROOT / "storage"))
settings.OSRM_HOST = os.getenv("OSRM_HOST", "localhost")
settings.OSRM_PORT = int(os.getenv("OSRM_PORT", "8080"))
settings.SIMULATOR_BINARY = os.getenv("SIMULATOR_BINARY", str(REPO_ROOT / "data" / "fire_simulator"))


def ensure_runtime_dirs() -> None:
    """Create runtime directories the app needs but cannot rely on being present.

    `storage/` (SQLite DB), `logs/` (per-run simulator output), and `data/` (input
    assets) are all gitignored. A fresh clone won't have them — the FastAPI app
    crashes on startup without `storage/`, and the worker can't write log dirs
    without `logs/`. Idempotent; safe to call repeatedly.
    """
    targets = [
        Path(settings.STORAGE_ROOT),
        REPO_ROOT / "logs",
        REPO_ROOT / "data",
    ]
    # Also ensure the SQLite file's parent exists when DATABASE_URL points to a
    # path outside STORAGE_ROOT.
    if settings.DATABASE_URL.startswith("sqlite:///"):
        db_path = Path(settings.DATABASE_URL.removeprefix("sqlite:///"))
        targets.append(db_path.parent)
    for d in targets:
        d.mkdir(parents=True, exist_ok=True)
