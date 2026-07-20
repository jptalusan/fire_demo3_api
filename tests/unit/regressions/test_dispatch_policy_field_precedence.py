"""Regression: `models.dispatch` is a dead field in the simulation config
mapping -- only the top-level `dispatch_policy` is read. This pins that
`models.dispatch` has NO effect at all (rather than silently taking
precedence, or being read as a fallback when `dispatch_policy` is absent), so
a future re-introduction of `models.dispatch` handling is a deliberate,
reviewed change and not an accidental resurrection of the redundant field
cleaned up earlier.

We patch asyncio.create_subprocess_exec (no real C++ simulator) and inspect
the --DISPATCH_POLICY argv entry.
"""

from __future__ import annotations

from pathlib import Path

from .conftest import arg_value, run_simulation_with_dirs

# `captured_subprocess_call` fixture comes from tests/unit/regressions/conftest.py


async def test_top_level_dispatch_policy_nearest_maps_to_nearest(
    tmp_path: Path, captured_subprocess_call
):
    config = {
        "models": {"incident": "irrelevant", "travelTime": "OSRM", "serviceTime": "ml_based"},
        "incident_type": "fire",
        "dispatch_policy": "nearest",
    }
    await run_simulation_with_dirs(tmp_path, config)
    assert arg_value(captured_subprocess_call["argv"], "--DISPATCH_POLICY") == "NEAREST"


async def test_models_dispatch_field_alone_is_ignored_falls_back_to_firebeats(
    tmp_path: Path, captured_subprocess_call
):
    """A payload with ONLY `models.dispatch='nearest'` (no top-level
    `dispatch_policy`) must NOT be honored. The mapping falls back to the
    top-level default, FIREBEATS."""
    config = {
        "models": {
            "incident": "irrelevant", "travelTime": "OSRM", "serviceTime": "ml_based",
            "dispatch": "nearest",  # dead field -- must be ignored
        },
        "incident_type": "fire",
        # no top-level dispatch_policy
    }
    await run_simulation_with_dirs(tmp_path, config)
    assert arg_value(captured_subprocess_call["argv"], "--DISPATCH_POLICY") == "FIREBEATS", (
        "models.dispatch was read even though top-level dispatch_policy handling is "
        "supposed to be the only source of truth -- if models.dispatch support was "
        "reintroduced deliberately, update this test to match."
    )
