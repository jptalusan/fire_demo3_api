import os
import socket
from pathlib import Path
import dotenv

dotenv.load_dotenv()


def _resolve_osrm_host(configured: str) -> str:
    """Return an OSRM_HOST that actually resolves at runtime.

    'host.docker.internal' is the canonical way to reach the docker host from
    inside a container, so we default to it in compose. On native macOS
    (Docker Desktop absent) and on plain Linux hosts that hostname doesn't
    resolve, which used to silently break the C++ simulator when someone ran
    uvicorn directly. Try the configured host; if getaddrinfo fails, fall
    back to localhost with a log line so the switch is visible."""
    try:
        socket.getaddrinfo(configured, None)
        return configured
    except OSError:
        print(
            f"[core.config] OSRM_HOST={configured!r} does not resolve; "
            "falling back to 'localhost'. Set OSRM_HOST explicitly if the "
            "OSRM server lives on a different host."
        )
        return "localhost"

# Define the project root directory. When the package is installed (e.g. via
# `uv pip install --system .` in Docker), __file__ resolves under site-packages
# and the parent chain points outside the project. Allow BASE_DIR to be set
# explicitly via env var to override that, and derive LOGS_DIR / DATA_DIR /
# SRC_DIR from it (each still independently overridable).
BASE_DIR = Path(os.getenv("BASE_DIR", str(Path(__file__).resolve().parent.parent.parent)))

# Define paths for data, logs, and source directories
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
LOGS_DIR = Path(os.getenv("LOGS_DIR", BASE_DIR / "logs"))
SRC_DIR = Path(os.getenv("SRC_DIR", BASE_DIR / "src"))
# POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]  #  os.environ raises an exception if the environmental variable does not exist

# POSTGRES_USER = os.getenv("POSTGRES_USER", "schoolride")
# POSTGRES_DB = os.getenv("POSTGRES_DB", "schoolride")
# POSTGRES_PORT = os.getenv("POSTGRES_PORT", 5432)
# POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")

ADMINER_PORT = os.getenv("ADMINER_PORT", 9090)
API_PORT = os.getenv("API_PORT", 8050)
# VALHALLA_PORT = os.getenv("VALHALLA_PORT", 8002)
OSRM_HOST = _resolve_osrm_host(os.getenv("OSRM_HOST", "localhost"))
OSRM_PORT = os.getenv("OSRM_PORT", 8080)
# VROOM_PORT = os.getenv("VROOM_PORT", 3000)
# VROOM_ROUTER = os.getenv("VROOM_ROUTER", "osrm")
