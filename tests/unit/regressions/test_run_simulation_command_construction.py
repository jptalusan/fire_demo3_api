"""Regression: FIREBEATS_MATRIX_PATH must point at the single shared
<BASE_DIR>/logs/beats.bin path, NOT at this run's per-job logs_dir.

Each job gets its own isolated logs_dir (so concurrent runs don't collide --
see the "Per-run isolated stations file" comment in engine/simulation.py),
but the firebeats matrix is expensive to build and must be shared/reused
across runs rather than rebuilt from scratch under a per-run path. Fixed
earlier this session in engine/simulation.py's sim_config construction.

We patch asyncio.create_subprocess_exec (no real C++ simulator) and inspect
the argv it was invoked with.
"""

from __future__ import annotations

from pathlib import Path

import core.config as constants

from .conftest import arg_value, run_simulation_with_dirs

# `captured_subprocess_call` fixture comes from tests/unit/regressions/conftest.py


async def test_firebeats_matrix_path_uses_shared_base_dir_not_per_run_logs_dir(
    tmp_path: Path, captured_subprocess_call
):
    config = {
        "models": {"incident": "irrelevant", "travelTime": "OSRM", "serviceTime": "ml_based"},
        "incident_type": "fire",
    }
    logs_dir = await run_simulation_with_dirs(tmp_path, config)

    argv = captured_subprocess_call["argv"]
    firebeats_path = arg_value(argv, "--FIREBEATS_MATRIX_PATH")

    expected = str(constants.BASE_DIR / "logs" / "beats.bin")
    assert firebeats_path == expected, (
        f"FIREBEATS_MATRIX_PATH={firebeats_path!r} should be the shared {expected!r}, "
        f"not something under this run's per-job logs_dir ({logs_dir})"
    )
    assert str(logs_dir) not in firebeats_path


async def test_dispatch_policy_argument_reflects_config(tmp_path: Path, captured_subprocess_call):
    config = {
        "models": {"incident": "irrelevant", "travelTime": "OSRM", "serviceTime": "ml_based"},
        "incident_type": "fire",
        "dispatch_policy": "nearest",
    }
    await run_simulation_with_dirs(tmp_path, config)

    argv = captured_subprocess_call["argv"]
    assert arg_value(argv, "--DISPATCH_POLICY") == "NEAREST"
