"""Preflight: every `--*_PATH` flag the simulator is launched with must
either exist under DATA_DIR/LOGS_DIR *or* be a path the C++ binary is
expected to produce at runtime.

This is the last line of defense against Incident 2 (FireBeats matrix
pointed at an empty per-run logs_dir) and Incident 9 (an operator changes
DATA_DIR but a hard-coded path still points at the old location).

We patch asyncio.create_subprocess_exec so no real simulator runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# --------------------------------------------------------------------------- #
# argv-capture fixture (self-contained; does not depend on the regressions
# conftest, so preflight can run on its own).
# --------------------------------------------------------------------------- #

@pytest.fixture
def captured_subprocess_call(monkeypatch):
    import engine.simulation as simulation

    calls: dict[str, Any] = {}

    async def _fake_create_subprocess_exec(*args, **kwargs):
        calls["argv"] = args
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 1  # short-circuit results processing
        return proc

    monkeypatch.setattr(simulation.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    return calls


async def _run_and_capture(tmp_path: Path, cfg: dict, captured):
    import engine.simulation as simulation
    data_dir = tmp_path / "data"; data_dir.mkdir()
    logs_dir = tmp_path / "logs"; logs_dir.mkdir()
    models_dir = tmp_path / "models"; models_dir.mkdir()
    await simulation.run_simulation_internal(cfg, data_dir, logs_dir, models_dir)
    return data_dir, logs_dir, models_dir


def _arg(argv: tuple, flag: str) -> str:
    prefix = f"{flag}="
    for a in argv:
        if isinstance(a, str) and a.startswith(prefix):
            return a[len(prefix):]
    raise AssertionError(f"{flag} not found in argv: {argv}")


# --------------------------------------------------------------------------- #
# Assertions
# --------------------------------------------------------------------------- #

# Flags whose target must resolve under the run's DATA_DIR (fixture files
# won't exist because we don't populate them, so we assert path *shape* --
# i.e. they resolve under the right root and use the expected basename).
DATA_DIR_FLAGS = [
    ("--BOUNDS_GEOJSON_PATH",      "bounds.geojson"),
    ("--NFD_RESPONSE_CSV_PATH",    "NFDResponse.csv"),
    ("--RESOLUTION_STATS_CSV_PATH","response_time_summary2.csv"),
    ("--ZONE_MAP_PATH",            "zones.csv"),
    ("--BEATS_SHAPEFILE_PATH",     "beats_shpfile.geojson"),
    ("--HOSPITALS_CSV_PATH",       "hospital_locations.csv"),
    ("--EMS_SCENE_TIME_STATS_PATH","scene_time_by_category.csv"),
]

# Flags whose target must resolve under this run's per-job LOGS_DIR (the C++
# binary produces them; here we just check they're written under the right
# place so concurrent runs don't collide).
LOGS_DIR_OUTPUT_FLAGS = [
    ("--REPORT_CSV_PATH",         "incident_report.csv"),
    ("--STATION_REPORT_CSV_PATH", "station_report.csv"),
    ("--DURATION_MATRIX_PATH",    "duration_matrix.bin"),
    ("--DISTANCE_MATRIX_PATH",    "distance_matrix.bin"),
    ("--MATRIX_CSV_PATH",         "matrix.csv"),
    ("--EMS_TRANSPORT_REPORT_PATH","ems_transport_report.csv"),
]


BASE_CONFIG = {
    "models": {"incident": "irrelevant", "travelTime": "OSRM", "serviceTime": "ml_based"},
    "incident_type": "fire",
}


async def test_all_data_dir_flags_resolve_under_run_data_dir(tmp_path: Path, captured_subprocess_call):
    data_dir, _, _ = await _run_and_capture(tmp_path, BASE_CONFIG, captured_subprocess_call)
    argv = captured_subprocess_call["argv"]
    for flag, basename in DATA_DIR_FLAGS:
        val = _arg(argv, flag)
        assert val.startswith(str(data_dir)), (
            f"\n{flag}={val!r} does not resolve under DATA_DIR={data_dir}. "
            f"Some caller is baking in a stale absolute path -- override with "
            f"DATA_DIR env var, or fix the engine to use `data_dir / ...`."
        )
        assert Path(val).name == basename, (
            f"{flag} basename drifted: got {Path(val).name!r}, expected {basename!r}."
        )


async def test_all_output_flags_resolve_under_run_logs_dir(tmp_path: Path, captured_subprocess_call):
    _, logs_dir, _ = await _run_and_capture(tmp_path, BASE_CONFIG, captured_subprocess_call)
    argv = captured_subprocess_call["argv"]
    for flag, basename in LOGS_DIR_OUTPUT_FLAGS:
        val = _arg(argv, flag)
        assert val.startswith(str(logs_dir)), (
            f"\n{flag}={val!r} does not resolve under this run's LOGS_DIR={logs_dir}. "
            f"Concurrent runs will collide -- output paths must be per-run."
        )
        assert Path(val).name == basename, (
            f"{flag} basename drifted: got {Path(val).name!r}, expected {basename!r}."
        )


async def test_firebeats_matrix_path_uses_shared_base_dir_not_per_run_logs_dir(
    tmp_path: Path, captured_subprocess_call
):
    """Motivating Incident 2: FIREBEATS matrix must be the shared file at
    <BASE_DIR>/logs/beats.bin, NOT under this run's per-job logs_dir --
    otherwise every fresh run tries to rebuild the matrix from scratch or
    errors 'FireBeats matrix file not found'."""
    import core.config as constants
    _, logs_dir, _ = await _run_and_capture(tmp_path, BASE_CONFIG, captured_subprocess_call)

    firebeats = _arg(captured_subprocess_call["argv"], "--FIREBEATS_MATRIX_PATH")
    expected = str(constants.BASE_DIR / "logs" / "beats.bin")
    assert firebeats == expected, (
        f"\n--FIREBEATS_MATRIX_PATH={firebeats!r} should equal the shared "
        f"{expected!r}, not something under this run's per-job logs_dir "
        f"({logs_dir}). Fix: engine/simulation.py -> sim_config['FIREBEATS_MATRIX_PATH']."
    )
    assert str(logs_dir) not in firebeats


async def test_apparatus_csv_uses_default_stations_when_no_stations_in_payload(
    tmp_path: Path, captured_subprocess_call
):
    data_dir, _, _ = await _run_and_capture(tmp_path, BASE_CONFIG, captured_subprocess_call)
    apparatus = _arg(captured_subprocess_call["argv"], "--APPARATUS_CSV_PATH")
    expected = str(data_dir / "stations_with_apparatus.csv")
    assert apparatus == expected, (
        f"\n--APPARATUS_CSV_PATH={apparatus!r}; expected the default roster at {expected!r}"
    )


async def test_apparatus_csv_uses_user_stations_when_stations_in_payload(
    tmp_path: Path, captured_subprocess_call
):
    cfg = {**BASE_CONFIG, "stations": [{
        "id": "0", "name": "S", "lat": 36.0, "lon": -86.0,
        "apparatus": [{"type": "Engine", "count": 1}],
    }]}
    _, logs_dir, _ = await _run_and_capture(tmp_path, cfg, captured_subprocess_call)
    apparatus = _arg(captured_subprocess_call["argv"], "--APPARATUS_CSV_PATH")
    expected = str(logs_dir / "user_stations.csv")
    assert apparatus == expected, (
        f"\n--APPARATUS_CSV_PATH={apparatus!r}; expected per-run user stations at "
        f"{expected!r}. Concurrent runs will collide if this isn't per-run."
    )
    assert (logs_dir / "user_stations.csv").is_file(), (
        "Per-run user_stations.csv wasn't actually written -- writer skipped or "
        "output_path drifted from --APPARATUS_CSV_PATH."
    )


async def test_incidents_csv_path_falls_back_to_incidents_small(
    tmp_path: Path, captured_subprocess_call
):
    """When no incident model is specified, engine.simulation falls back to
    <DATA_DIR>/incidents_small.csv. This asserts the fallback still points
    under the run's DATA_DIR (not a hard-coded path)."""
    data_dir, _, _ = await _run_and_capture(tmp_path, BASE_CONFIG, captured_subprocess_call)
    incidents = _arg(captured_subprocess_call["argv"], "--INCIDENTS_CSV_PATH")
    assert incidents.startswith(str(data_dir)), (
        f"\n--INCIDENTS_CSV_PATH={incidents!r} escapes DATA_DIR={data_dir}."
    )
