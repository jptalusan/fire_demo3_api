"""Job processing: dispatch by kind, run via Simulator, persist outputs.

The Simulator is injected as a factory (`sim_factory`) so callers (the worker
loop, the tests) decide which concrete implementation runs — no monkey-patching
of module globals.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session

import core.config as constants
from backend.services.simulator import (
    Simulator,
    SimulatorRunRequest,
    default_simulator,
    run_parallel,
)
from db import crud
from db.models import Job
from db.session import SessionLocal
from db.storage import LocalStorage
from engine.simulation import calculate_comparison_stats

logger = logging.getLogger("worker.processor")

# Hard cap on a single job. A non-terminating run (e.g. a station config that
# can't resolve incidents) is cancelled instead of hanging the worker forever.
JOB_TIMEOUT_SEC = float(os.getenv("JOB_TIMEOUT_SEC", "3600"))

# How often the cancel watchdog polls the DB for the cancel flag, in seconds.
# Configurable for tests (which want sub-second responsiveness).
CANCEL_POLL_SEC = float(os.getenv("CANCEL_POLL_SEC", "2.0"))


SimFactory = Callable[[], Simulator]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_job(
    db: Session,
    job: Job,
    *,
    sim_factory: SimFactory = default_simulator,
    timeout_sec: float = JOB_TIMEOUT_SEC,
    cancel_poll_sec: float = CANCEL_POLL_SEC,
    logs_root: Optional[Path] = None,
) -> None:
    """Run a single job to completion (or failure). Updates the DB row in-place.

    All collaborators (sim, timeout, poll cadence, logs root) are injected so
    tests don't have to reach in and patch module globals.
    """
    started = time.monotonic()
    root = Path(logs_root) if logs_root is not None else constants.BASE_DIR
    try:
        coro = _dispatch(job, sim_factory, root)
        result = asyncio.run(_run_with_timeout_and_cancel(coro, job.id, timeout_sec, cancel_poll_sec))

        if isinstance(result, dict):
            result["duration_seconds"] = round(time.monotonic() - started, 2)

        sim_error = _extract_sim_error(result)
        if sim_error:
            logger.error(f"Job {job.id} failed in simulator: {sim_error[:200]}")
            crud.mark_job_failed(db, job.id, sim_error)
            return

        _persist_outputs(job.id, result)
        crud.mark_job_done(db, job.id, result)
        logger.info(f"Job {job.id} done in {time.monotonic() - started:.1f}s.")
    except _CancelledByUser:
        msg = "Cancelled by user."
        logger.info(f"Job {job.id} cancelled by user after {time.monotonic() - started:.1f}s")
        crud.mark_job_failed(db, job.id, msg)
    except (asyncio.TimeoutError, TimeoutError):
        msg = (
            f"Job exceeded the {timeout_sec:.0f}s limit and was cancelled. "
            "This usually means the simulation can't terminate — e.g. a station "
            "configuration with no apparatus able to resolve some incident types "
            "(check that fire incidents have an Engine, EMS have a Medic)."
        )
        logger.error(f"Job {job.id} timed out after {timeout_sec:.0f}s")
        crud.mark_job_failed(db, job.id, msg)
    except Exception as exc:
        logger.exception(f"Job {job.id} failed: {exc}")
        crud.mark_job_failed(db, job.id, str(exc))


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

class _CancelledByUser(Exception):
    """Raised by the watchdog when a user has requested cancellation."""


def _dispatch(job: Job, sim_factory: SimFactory, logs_root: Path):
    if job.kind == "run-simulation":
        return _run_simulation(job, sim_factory(), logs_root)
    if job.kind == "run-comparison":
        return _run_comparison(job, sim_factory(), logs_root)
    raise ValueError(f"Unknown job kind: {job.kind}")


async def _run_with_timeout_and_cancel(coro, job_id: int, timeout_sec: float, poll_sec: float):
    """Race the work against (a) a per-job timeout and (b) a cancellation watchdog.

    The watchdog opens its OWN DB session each tick (the main one belongs to the
    worker loop). If the user requests cancellation, the watchdog raises
    `_CancelledByUser` and the work task is cancelled — `run_simulation_internal`
    handles `asyncio.CancelledError` by killing the C++ child process.
    """
    work_task = asyncio.create_task(coro, name=f"job-{job_id}-work")
    watch_task = asyncio.create_task(_watch_cancel(job_id, poll_sec), name=f"job-{job_id}-watch")

    try:
        done, _pending = await asyncio.wait(
            {work_task, watch_task},
            timeout=timeout_sec,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            # Timeout fired. Cancel both.
            raise asyncio.TimeoutError()
        if watch_task in done:
            # Watchdog fired (cancel requested) or errored.
            watch_task.result()  # re-raise _CancelledByUser
            return None  # unreachable
        # Work finished first — get its result.
        return work_task.result()
    finally:
        for t in (work_task, watch_task):
            if not t.done():
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass


async def _watch_cancel(job_id: int, poll_sec: float) -> None:
    """Poll the DB for cancel_requested. Raise _CancelledByUser when seen."""
    while True:
        await asyncio.sleep(poll_sec)
        db = SessionLocal()
        try:
            if crud.is_cancel_requested(db, job_id):
                raise _CancelledByUser()
        finally:
            db.close()


def _extract_sim_error(result) -> Optional[str]:
    """Pick out an error message from a simulator/comparison result, if any.

    Per-leg dicts carry the real message in a comparison; check them first.
    """
    if not isinstance(result, dict):
        return None
    for leg in ("baseline", "newConfig"):
        sub = result.get(leg)
        if isinstance(sub, dict) and sub.get("status") == "error":
            return f"{leg}: {sub.get('error') or 'status=error'}"
    if result.get("status") == "error":
        return str(result.get("error") or "Simulation returned status=error with no message")
    return None


def _isolate_paths(config: dict, run_dir: Path) -> dict:
    """Rewrite every write path in the simulator config to live under run_dir.

    Caller is responsible for creating run_dir. Idempotent if called twice.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    overrides = {
        "REPORT_CSV_PATH": str(run_dir / "incident_report.csv"),
        "STATION_REPORT_CSV_PATH": str(run_dir / "station_report.csv"),
        "EMS_TRANSPORT_REPORT_PATH": str(run_dir / "ems_transport_report.csv"),
        "DURATION_MATRIX_PATH": str(run_dir / "duration_matrix.bin"),
        "DISTANCE_MATRIX_PATH": str(run_dir / "distance_matrix.bin"),
        "MATRIX_CSV_PATH": str(run_dir / "matrix.csv"),
        "FIREBEATS_MATRIX_PATH": str(run_dir / "beats.bin"),
    }
    cfg = dict(config)
    cfg.update(overrides)
    return cfg


async def _run_simulation(job: Job, sim: Simulator, logs_root: Path) -> dict:
    config = job.payload.get("config") or job.payload
    logs_dir = Path(job.payload.get("logs_dir") or (logs_root / "logs" / f"job_{job.id}"))
    config = _isolate_paths(config, logs_dir)
    res = await sim.run(
        SimulatorRunRequest(
            config=config,
            data_dir=constants.DATA_DIR,
            logs_dir=logs_dir,
            models_dir=constants.DATA_DIR / "models",
            config_name=f"job_{job.id}",
        )
    )
    return res.raw


async def _run_comparison(job: Job, sim: Simulator, logs_root: Path) -> dict:
    baseline = job.payload.get("baseline") or {}
    new_cfg = job.payload.get("newConfig") or {}
    base_dir = logs_root / "logs" / f"job_{job.id}"
    b_dir, n_dir = base_dir / "baseline", base_dir / "newconfig"
    baseline = _isolate_paths(baseline, b_dir)
    new_cfg = _isolate_paths(new_cfg, n_dir)
    baseline_res, new_res = await run_parallel(
        sim,
        SimulatorRunRequest(config=baseline, data_dir=constants.DATA_DIR, logs_dir=b_dir, models_dir=constants.DATA_DIR / "models", config_name="baseline"),
        SimulatorRunRequest(config=new_cfg, data_dir=constants.DATA_DIR, logs_dir=n_dir, models_dir=constants.DATA_DIR / "models", config_name="newconfig"),
    )
    comparison = calculate_comparison_stats(baseline_res.raw, new_res.raw)
    return {
        "status": "success" if (baseline_res.succeeded and new_res.succeeded) else "error",
        "baseline": baseline_res.raw,
        "newConfig": new_res.raw,
        "comparison": comparison,
    }


def _persist_outputs(job_id: int, result: dict) -> None:
    """Copy any file paths referenced in result into job's storage/output/ dir."""
    LocalStorage.mkdirs(job_id)
    candidates: list[Path] = []
    for key in ("REPORT_CSV_PATH", "STATION_REPORT_CSV_PATH", "EMS_TRANSPORT_REPORT_PATH"):
        p = result.get(key)
        if isinstance(p, str):
            candidates.append(Path(p))
    if candidates:
        LocalStorage.copy_outputs(job_id, candidates)
