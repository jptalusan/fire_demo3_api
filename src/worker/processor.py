"""Job processing: dispatch by kind, run via Simulator, persist outputs."""

import asyncio
import logging
import os
import shutil
import time
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

import core.config as constants
from backend.services.simulator import (
    SimulatorRunRequest,
    default_simulator,
    run_parallel,
)
from db import crud
from db.models import Job
from db.storage import LocalStorage
from engine.simulation import calculate_comparison_stats

logger = logging.getLogger("worker.processor")

# Hard cap on a single job. A non-terminating run (e.g. a station config that
# can't resolve incidents) is cancelled instead of hanging the worker forever.
# Legit long runs (a month of incidents ~13 min) fit under the default.
JOB_TIMEOUT_SEC = float(os.getenv("JOB_TIMEOUT_SEC", "3600"))


async def _with_timeout(coro):
    return await asyncio.wait_for(coro, JOB_TIMEOUT_SEC)


def process_job(db: Session, job: Job) -> None:
    started = time.monotonic()
    try:
        if job.kind == "run-simulation":
            result = asyncio.run(_with_timeout(_run_simulation(job)))
        elif job.kind == "run-comparison":
            result = asyncio.run(_with_timeout(_run_comparison(job)))
        else:
            raise ValueError(f"Unknown job kind: {job.kind}")

        # Persist how long the simulation took inside the stored result blob too.
        if isinstance(result, dict):
            result["duration_seconds"] = round(time.monotonic() - started, 2)
        _persist_outputs(job.id, result)
        crud.mark_job_done(db, job.id, result)
        logger.info(f"Job {job.id} done in {time.monotonic() - started:.1f}s.")
    except (asyncio.TimeoutError, TimeoutError):
        msg = (
            f"Job exceeded the {JOB_TIMEOUT_SEC:.0f}s limit and was cancelled. "
            "This usually means the simulation can't terminate — e.g. a station "
            "configuration with no apparatus able to resolve some incident types "
            "(check that fire incidents have an Engine, EMS have a Medic)."
        )
        logger.error(f"Job {job.id} timed out after {JOB_TIMEOUT_SEC:.0f}s")
        crud.mark_job_failed(db, job.id, msg)
    except Exception as exc:
        logger.exception(f"Job {job.id} failed: {exc}")
        crud.mark_job_failed(db, job.id, str(exc))


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


async def _run_simulation(job: Job) -> dict:
    sim = default_simulator()
    config = job.payload.get("config") or job.payload
    logs_dir = Path(job.payload.get("logs_dir") or (constants.BASE_DIR / "logs" / f"job_{job.id}"))
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


async def _run_comparison(job: Job) -> dict:
    sim = default_simulator()
    baseline = job.payload.get("baseline") or {}
    new_cfg = job.payload.get("newConfig") or {}
    # Deterministic per-job dir (not a random uuid) so the progress endpoint can
    # locate this job's sim.log / progress.json while it runs.
    base_dir = constants.BASE_DIR / "logs" / f"job_{job.id}"
    b_dir, n_dir = base_dir / "baseline", base_dir / "newconfig"
    baseline = _isolate_paths(baseline, b_dir)
    new_cfg = _isolate_paths(new_cfg, n_dir)
    # Parallel: both legs run at once (halves wall-clock vs series). Still one
    # job at a time globally; this concurrency is within this comparison job.
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
