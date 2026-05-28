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
settings.OSRM_PORT = int(os.getenv("OSRM_PORT", "5000"))
settings.SIMULATOR_BINARY = os.getenv("SIMULATOR_BINARY", str(REPO_ROOT / "data" / "fire_simulator"))
