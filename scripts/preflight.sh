#!/usr/bin/env bash
#
# scripts/preflight.sh - fail fast on config/data errors before uvicorn starts.
#
# Runs in two phases:
#   1. Required-files check (< 1s) -- if any expected file is missing under
#      DATA_DIR or LOGS_DIR, the whole suite bails out immediately with the
#      offending path + the env var that would move it.
#   2. Rest of tests/preflight (< 5s total) -- CSV column schema, env
#      resolution, payload validation, simulator argv, docker-compose wiring.
#
# Failure classes and which test file covers them:
#   Missing files / bad paths           -> test_required_files_present.py
#   CSV column drift / bad categories   -> test_csv_column_schema.py
#   Bad BASE_DIR/DATA_DIR/LOGS_DIR env  -> test_env_config_resolution.py
#   Malformed payloads                  -> test_payload_validation.py
#   Simulator argv wired wrong          -> test_simulator_command_paths.py
#   docker-compose.yml gaps             -> test_docker_compose_config.py
#
# Exit codes: 0 on green, non-zero if anything blocks a deploy.

set -u

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

BASE_DIR_RESOLVED="${BASE_DIR:-$repo_root}"
DATA_DIR_RESOLVED="${DATA_DIR:-$BASE_DIR_RESOLVED/data}"
LOGS_DIR_RESOLVED="${LOGS_DIR:-$BASE_DIR_RESOLVED/logs}"

echo "======================================================================"
echo " fire_demo3_api preflight"
echo "----------------------------------------------------------------------"
echo "  BASE_DIR = $BASE_DIR_RESOLVED"
echo "  DATA_DIR = $DATA_DIR_RESOLVED"
echo "  LOGS_DIR = $LOGS_DIR_RESOLVED"
echo "======================================================================"

# Pick a Python interpreter: honour $PYTHON if set (e.g. inside a venv),
# else fall back to python3 (macOS Homebrew, most Linux distros) or python.
PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON=python3
    elif command -v python >/dev/null 2>&1; then
        PYTHON=python
    else
        echo "PREFLIGHT: no python interpreter found on PATH. Set PYTHON=/path/to/python." >&2
        exit 2
    fi
fi

# Resolve a pytest runner. Preference order:
#   1. `pytest` on PATH (already inside a venv or globally installed)
#   2. `$PYTHON -m pytest` (venv activated but shim missing)
#   3. `uv run pytest` (local dev via uv — pulls the project's env)
PYTEST_CMD=""
if command -v pytest >/dev/null 2>&1; then
    PYTEST_CMD="pytest"
elif "$PYTHON" -c "import pytest" >/dev/null 2>&1; then
    PYTEST_CMD="$PYTHON -m pytest"
elif command -v uv >/dev/null 2>&1; then
    PYTEST_CMD="uv run pytest"
else
    echo "PREFLIGHT: no pytest available. Install with 'pip install pytest' or run this script inside the project's venv." >&2
    exit 2
fi

echo
echo "[1/2] required files (fail-fast) ..."
$PYTEST_CMD tests/preflight/test_required_files_present.py -q -m "not optional" --no-header
phase1=$?
if [[ $phase1 -ne 0 ]]; then
    echo
    echo "----------------------------------------------------------------------"
    echo "PREFLIGHT FAILED at phase 1 (required files)."
    echo "See the failures above -- each names the missing path and the env var"
    echo "you can set to point it somewhere else (DATA_DIR / LOGS_DIR)."
    echo "----------------------------------------------------------------------"
    exit $phase1
fi

echo
echo "[2/2] configuration + schema + argv + compose ..."
$PYTEST_CMD tests/preflight -v -m "not optional" --no-header
phase2=$?
echo
if [[ $phase2 -ne 0 ]]; then
    echo "----------------------------------------------------------------------"
    echo "PREFLIGHT FAILED at phase 2. Common fixes:"
    echo "  - CSV header drift?   see tests/preflight/test_csv_column_schema.py"
    echo "  - Env resolution?     see tests/preflight/test_env_config_resolution.py"
    echo "  - Bad payload shape?  see tests/preflight/test_payload_validation.py"
    echo "  - Wrong simulator --*_PATH? see test_simulator_command_paths.py"
    echo "  - docker-compose gap? see tests/preflight/test_docker_compose_config.py"
    echo "----------------------------------------------------------------------"
    exit $phase2
fi

# Optional phase 3: if a docker stack is currently running, verify each
# container's bind-mounted CSVs actually match what the host file contains.
# Catches the "docker resolved a symlink at container start, then the symlink
# target changed" class of bug where the container serves stale data long
# after `git pull` or a CSV edit. Skips gracefully if docker isn't running
# or no matching containers are up.
if command -v docker >/dev/null 2>&1 \
   && docker compose ps --format '{{.Name}}' 2>/dev/null | grep -qE '_(backend|worker)$'
then
    echo
    echo "[3/3] runtime bind-mount check (containers detected) ..."
    bash "$(dirname "$0")/check_bind_mounts.sh"
    phase3=$?
    if [[ $phase3 -ne 0 ]]; then
        echo
        echo "----------------------------------------------------------------------"
        echo "PREFLIGHT FAILED at phase 3 (runtime bind mounts)."
        echo "The container's view of a CSV does not match the host file at the"
        echo "compose-declared bind source. Fix printed above."
        echo "----------------------------------------------------------------------"
        exit $phase3
    fi
fi

echo "======================================================================"
echo "  PREFLIGHT PASSED -- safe to start uvicorn / docker compose up."
echo "======================================================================"
exit 0
