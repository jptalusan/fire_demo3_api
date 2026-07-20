"""Shared fixtures for tests/unit/regressions.

These tests never touch the real DB, the real C++ simulator, real OSRM, or the
real growth_v1 model bundle. Everything above the pure-function layer is
either monkeypatched or exercised through fixture data written to tmp_path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.auth import get_current_user

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_DATA_DIR = REPO_ROOT / "data"


@pytest.fixture
def data_dir_with_fixture_csvs(tmp_path: Path) -> Path:
    """A tmp DATA_DIR containing a minimal stations CSV + NFDResponse CSV.

    Headers are copied verbatim from the real data files so tests here catch
    column drift against production data rather than drifting along with a
    hand-maintained fixture header.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    stations_header = (REAL_DATA_DIR / "stations_with_apparatus.csv").read_text().splitlines()[0]
    (data_dir / "stations_with_apparatus.csv").write_text(
        stations_header + "\n"
        "0,Station 01,36.2293898,-86.75674762,130 Broadmoor Avenue,1,,1,,1,,,,,,,,\n"
    )

    nfd_header = (REAL_DATA_DIR / "NFDResponse.csv").read_text().splitlines()[0]
    (data_dir / "NFDResponse.csv").write_text(nfd_header + "\n")

    return data_dir


@pytest.fixture
def authed_client() -> Iterator[TestClient]:
    """TestClient with `get_current_user` overridden to a fixed user id.

    `raise_server_exceptions=False` so unhandled-exception routes surface as
    real HTTP 500 responses instead of re-raising into the test -- needed by
    the error-shape regression tests (see test_error_response_shapes.py).
    """
    app.dependency_overrides[get_current_user] = lambda: 1
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


def make_fake_process(returncode: int = 1) -> MagicMock:
    """A minimal stand-in for the asyncio.subprocess.Process returned by
    asyncio.create_subprocess_exec, good enough for run_simulation_internal's
    `await process.communicate()` / `process.returncode` usage."""
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.returncode = returncode
    return proc


@pytest.fixture
def captured_subprocess_call(monkeypatch):
    """Patch engine.simulation's asyncio.create_subprocess_exec and capture
    the positional argv it was called with, without running any real
    subprocess (no C++ simulator, no OSRM)."""
    import engine.simulation as simulation

    calls: dict[str, Any] = {}

    async def _fake_create_subprocess_exec(*args, **kwargs):
        calls["argv"] = args
        return make_fake_process()

    monkeypatch.setattr(simulation.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    return calls


def arg_value(argv: tuple, flag: str) -> str:
    """Pull `--FLAG=value` out of a captured argv tuple."""
    prefix = f"{flag}="
    for a in argv:
        if isinstance(a, str) and a.startswith(prefix):
            return a[len(prefix):]
    raise AssertionError(f"{flag} not found in argv: {argv}")


async def run_simulation_with_dirs(tmp_path: Path, config: dict) -> Path:
    """Call run_simulation_internal with fresh tmp data/logs/models dirs.
    Returns logs_dir. Caller must already have patched
    asyncio.create_subprocess_exec (e.g. via captured_subprocess_call)."""
    import engine.simulation as simulation

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(exist_ok=True)
    models_dir = tmp_path / "models"
    models_dir.mkdir(exist_ok=True)
    await simulation.run_simulation_internal(config, data_dir, logs_dir, models_dir)
    return logs_dir
