"""Simulator service. Abstract interface + concrete C++ subprocess implementation.

The fire_demo3 simulator is a compiled C++ binary invoked with CLI flags. This
module hides that detail behind a `Simulator` ABC so the engine routes and worker
both consume a uniform API. A future native-Python or RPC simulator can replace
`CppSubprocessSimulator` without changing callers.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from engine.simulation import run_simulation_internal


@dataclass
class SimulatorRunRequest:
    config: dict[str, Any]
    data_dir: Path
    logs_dir: Path
    models_dir: Path
    config_name: str = "default"


@dataclass
class SimulatorRunResult:
    status: str
    raw: dict[str, Any]

    @property
    def succeeded(self) -> bool:
        return self.status == "success"


class Simulator(ABC):
    """Run-a-simulation interface."""

    @abstractmethod
    async def run(self, req: SimulatorRunRequest) -> SimulatorRunResult: ...


class CppSubprocessSimulator(Simulator):
    """Wraps fire_demo3's C++ simulator binary via `engine.run_simulation_internal`."""

    def __init__(self, binary_path: Optional[Path] = None) -> None:
        self.binary_path = binary_path

    async def run(self, req: SimulatorRunRequest) -> SimulatorRunResult:
        req.logs_dir.mkdir(parents=True, exist_ok=True)
        raw = await run_simulation_internal(
            config=req.config,
            data_dir=req.data_dir,
            logs_dir=req.logs_dir,
            models_dir=req.models_dir,
            config_name=req.config_name,
        )
        return SimulatorRunResult(status=raw.get("status", "error"), raw=raw)


def default_simulator() -> Simulator:
    """Factory used by routes/worker."""
    return CppSubprocessSimulator()


async def run_parallel(
    sim: Simulator,
    *reqs: SimulatorRunRequest,
) -> tuple[SimulatorRunResult, ...]:
    """Run scenarios concurrently (used for a comparison's two legs).

    The legs share the OSRM service, so they can contend under heavy load — but
    this halves the comparison's wall-clock vs running them in series. The global
    queue still ensures only one *job* runs at a time; this concurrency is within
    that single job.
    """
    return tuple(await asyncio.gather(*(sim.run(req) for req in reqs)))
