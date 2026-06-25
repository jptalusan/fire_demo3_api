import os
from pathlib import Path
import dotenv

dotenv.load_dotenv()

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
OSRM_HOST = os.getenv("OSRM_HOST", "localhost")
OSRM_PORT = os.getenv("OSRM_PORT", 8080)
# VROOM_PORT = os.getenv("VROOM_PORT", 3000)
# VROOM_ROUTER = os.getenv("VROOM_ROUTER", "osrm")
