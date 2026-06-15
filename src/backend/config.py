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
    # When True (the default), POST /auth/portal-login accepts a bare username
    # and issues a session for it (creating the user on first use). Intended
    # for deployments where an upstream portal has already authenticated the
    # caller and the backend trusts that portal. Set PORTAL_AUTH_ENABLED=false
    # to lock the endpoint down (it then returns 404).
    PORTAL_AUTH_ENABLED: bool
    CORS_ALLOWED_ORIGINS: list[str]
    COOKIE_SAMESITE: str   # "lax" (same-site) or "none" (cross-site; requires Secure)
    COOKIE_SECURE: bool    # True for HTTPS-only cookies (required when SameSite=None)


_DEFAULT_DEV_ORIGINS = [
    "http://localhost:3000",  "http://127.0.0.1:3000",
    "http://localhost:5173",  "http://127.0.0.1:5173",
    "http://localhost:8000",  "http://127.0.0.1:8000",
]


def _parse_origins(raw: str | None) -> list[str]:
    """Comma-separated list of allowed CORS origins. Empty/unset -> dev defaults.

    Use the literal string `*` to allow everything (NOT compatible with
    credentialed requests — set ALLOW_CREDENTIALS=false too in that case).
    """
    if not raw:
        return _DEFAULT_DEV_ORIGINS
    return [o.strip() for o in raw.split(",") if o.strip()]


def _truthy(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


settings = Settings()
settings.DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{REPO_ROOT}/storage/app.db")
settings.SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
settings.MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "5"))
settings.STORAGE_ROOT = os.getenv("STORAGE_ROOT", str(REPO_ROOT / "storage"))
settings.OSRM_HOST = os.getenv("OSRM_HOST", "localhost")
settings.OSRM_PORT = int(os.getenv("OSRM_PORT", "8080"))
settings.SIMULATOR_BINARY = os.getenv("SIMULATOR_BINARY", str(REPO_ROOT / "data" / "fire_simulator"))
settings.PORTAL_AUTH_ENABLED = os.getenv("PORTAL_AUTH_ENABLED", "true").lower() in ("1", "true", "yes")
settings.CORS_ALLOWED_ORIGINS = _parse_origins(os.getenv("CORS_ALLOWED_ORIGINS"))
settings.COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()
settings.COOKIE_SECURE = _truthy(
    os.getenv("COOKIE_SECURE"),
    default=(settings.COOKIE_SAMESITE == "none"),  # SameSite=None mandates Secure
)


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
