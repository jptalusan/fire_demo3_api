"""Shared fixtures + config for tests/preflight.

Preflight tests answer one question: "Would a docker run of the backend
actually succeed with what's on disk right now?" They inspect the *real*
data/, logs/, docker-compose.yml, and .env of the checkout under test --
so nothing here mocks the filesystem globally. The one exception is
`test_simulator_command_paths.py`, which patches asyncio's
create_subprocess_exec so we can inspect the argv the simulator would be
launched with without actually running the C++ binary.

Marker convention:
- `@pytest.mark.optional` for checks that only matter when a
  predictive/synthetic flow is exercised (growth_poisson_v1 bundle,
  incident_prediction_system trees). Skip them with `-m "not optional"`
  on a minimally-provisioned box.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "optional: preflight check that is only relevant when predictive "
        "or synthetic flows are used (growth_poisson_v1 bundle, incident "
        "prediction system). Skip with `-m 'not optional'`.",
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the fire_demo3_api checkout under test."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def real_data_dir(repo_root: Path) -> Path:
    """The DATA_DIR the running container/uvicorn would resolve to on this box.

    Honors the DATA_DIR env override the same way core.config does, so
    running preflight against a docker layout (DATA_DIR=/app/data) still
    inspects the right tree.
    """
    import os
    return Path(os.getenv("DATA_DIR", str(repo_root / "data")))


@pytest.fixture(scope="session")
def real_logs_dir(repo_root: Path) -> Path:
    import os
    return Path(os.getenv("LOGS_DIR", str(repo_root / "logs")))
