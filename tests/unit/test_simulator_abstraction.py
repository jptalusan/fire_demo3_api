"""Unit tests for the Simulator abstraction."""

from pathlib import Path

import pytest

from backend.services.simulator import (
    Simulator,
    SimulatorRunRequest,
    SimulatorRunResult,
    run_parallel,
)


class FakeSimulator(Simulator):
    def __init__(self, raw=None):
        self.calls: list[SimulatorRunRequest] = []
        self.raw = raw or {"status": "success", "total_incidents": 0}

    async def run(self, req: SimulatorRunRequest) -> SimulatorRunResult:
        self.calls.append(req)
        return SimulatorRunResult(status=self.raw["status"], raw=self.raw)


@pytest.mark.asyncio
async def test_simulator_run_returns_result(tmp_path):
    sim = FakeSimulator()
    req = SimulatorRunRequest(
        config={"a": 1},
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        models_dir=tmp_path / "models",
    )
    res = await sim.run(req)
    assert res.succeeded
    assert sim.calls == [req]


@pytest.mark.asyncio
async def test_run_parallel_runs_both_legs(tmp_path):
    sim = FakeSimulator()
    a = SimulatorRunRequest(config={"k": "baseline"}, data_dir=tmp_path, logs_dir=tmp_path, models_dir=tmp_path)
    b = SimulatorRunRequest(config={"k": "new"}, data_dir=tmp_path, logs_dir=tmp_path, models_dir=tmp_path)
    ra, rb = await run_parallel(sim, a, b)
    assert ra.succeeded and rb.succeeded
    assert {c.config["k"] for c in sim.calls} == {"baseline", "new"}


def test_failed_result_propagates():
    res = SimulatorRunResult(status="error", raw={"status": "error", "error": "x"})
    assert not res.succeeded
