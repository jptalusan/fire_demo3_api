"""Per-job filesystem layout for artifacts."""

import os
import shutil
from pathlib import Path
from typing import Iterable

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "./storage")).resolve()


class LocalStorage:
    """Filesystem storage for job inputs and outputs.

    Layout:
        STORAGE_ROOT/jobs/<job_id>/
            input/
            output/
    """

    @staticmethod
    def job_dir(job_id: int | str) -> Path:
        return STORAGE_ROOT / "jobs" / str(job_id)

    @staticmethod
    def mkdirs(job_id: int | str) -> Path:
        d = LocalStorage.job_dir(job_id)
        (d / "input").mkdir(parents=True, exist_ok=True)
        (d / "output").mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def output_dir(job_id: int | str) -> Path:
        return LocalStorage.job_dir(job_id) / "output"

    @staticmethod
    def copy_outputs(job_id: int | str, files: Iterable[Path]) -> list[str]:
        out = LocalStorage.output_dir(job_id)
        out.mkdir(parents=True, exist_ok=True)
        stored: list[str] = []
        for f in files:
            p = Path(f)
            if not p.exists():
                continue
            dest = out / p.name
            shutil.copy(p, dest)
            stored.append(str(dest))
        return stored
