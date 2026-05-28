# fire_demo3_api_v2

Fire/EMS dispatch simulator backend, restructured to match an industry-standard
layout: FastAPI + cookie-based JWT auth + SQLite-backed job queue + a background
worker that drives the existing C++ simulator. Full API contract in
[`API_REFERENCE.md`](./API_REFERENCE.md).

## Layout

```
src/
  backend/        FastAPI app
    main.py       app factory + startup hook
    config.py     env-driven Settings; ensure_runtime_dirs()
    routes/       auth, jobs, incidents, stations, system
    schemas/      pydantic models (auth, sim, incidents)
    services/     auth (bcrypt + JWT), simulator (ABC + C++ subprocess impl)
  db/             SQLAlchemy ORM, session, crud, local storage
  engine/         Simulator wrapping (calls the C++ binary, parses results)
  core/           Path constants
  worker/         Polls DB for pending jobs and runs them
tests/
  unit/  integration/  e2e/   (121 tests)
storage/          SQLite DB + per-job artifact dirs    (gitignored)
data/             Static inputs (incidents, stations, models, geojson) — gitignored
logs/             Per-run simulator output             (gitignored)
```

## Key differences vs. fire_demo3_api

| Concern | fire_demo3_api | fire_demo3_api_v2 |
|---|---|---|
| Persistence | Files only | SQLite + files |
| Auth | None | JWT + bcrypt |
| Job model | Sync `await` in HTTP request | DB job row, worker picks up |
| Simulator coupling | Inline subprocess call | `Simulator` ABC; `CppSubprocessSimulator` impl |
| Concurrency | One sim per request | One job at a time globally (queue gate) |
| Failure mode | Crash / hang | Per-job timeout (1h) + reaper for orphans |
| Tests | One notebook | `tests/{unit,integration,e2e}`, 121 tests |
| Deploy | Manual uvicorn | `docker-compose` (backend + worker + OSRM) |

## Prerequisites

- Python **3.10+** (the package targets `>=3.10`; tested on 3.11)
- The compiled C++ simulator binary at `data/fire_simulator` (executable; not in the repo)
- The data assets under `data/` (incidents, stations, ONNX models, interpolation matrices,
  ems_stats, geojson). Easiest: copy `data/` from a working `fire_demo3_api` checkout.
- A reachable OSRM service (the bundled `docker-compose.yml` brings one up on host port `8080`).
- Optional: Node 18+ if you want to run the React frontend.

## Quickstart (local, no Docker)

```bash
cp .env.example .env
# Edit .env if needed (SECRET_KEY in prod, OSRM_HOST/PORT).

python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # `uv pip install -e ".[dev]"` works the same

# Drop data/ assets in place. The runtime dirs (storage/, logs/, data/) are
# auto-created on startup, but the *files* under data/ must come from you.

# Terminal 1 — API on :8000
uvicorn backend.main:app --port 8000

# Terminal 2 — worker that runs the jobs
python -m worker.main
```

Verify:
```bash
curl http://localhost:8000/health        # {"status":"ok"}
open  http://localhost:8000/docs         # interactive API docs
```

## Quickstart (Docker)

```bash
cp .env.example .env
docker compose up --build
```
Brings up backend, worker, and OSRM (host port 8080). The `data/` and `storage/`
directories on the host are mounted into the containers, so put your data
assets there first.

## Auth + jobs flow

All `/api/*` endpoints require a session cookie set by `POST /auth/login`.

```
POST /auth/register   {username, password}                  → user
POST /auth/login      {username, password}                  → cookie + token
GET  /auth/me                                               → current user
POST /api/jobs        {kind, payload, priority}             → pending job
GET  /api/jobs/{id}/progress                                → live progress
GET  /api/jobs/{id}                                         → poll until done
GET  /api/jobs                                              → your history
GET  /api/jobs/queue/status                                 → queue snapshot
```

Simulations run **only** via the job queue — there are no synchronous engine
endpoints. The worker enforces a global "one job at a time" gate; a comparison
job runs its two legs in parallel within that single slot.

See [`API_REFERENCE.md`](./API_REFERENCE.md) for the full payload schema, every
enum, and the result shapes for `run-simulation` / `run-comparison`.

## Tests

```bash
PYTHONPATH=src DATABASE_URL=sqlite:///:memory: SECRET_KEY=test STORAGE_ROOT=/tmp/fd3v2_test \
  pytest tests/ -q
```

The suite (121 tests, ~15s) covers auth, crud, jobs, worker, schemas, routes,
and the global-serialization / stale-reaper logic. It uses an in-memory SQLite
DB and a fake `Simulator`, so it never invokes the real C++ binary or OSRM.

## Troubleshooting

- **`sqlite3.OperationalError: unable to open database file`** — fixed in newer
  versions (the app creates `storage/`, `logs/`, `data/` on startup). On old
  builds, run `mkdir -p storage logs data` first.
- **Job stays `pending` forever** — the worker isn't running. Start
  `python -m worker.main`.
- **Job `failed` with `Orphaned: no live worker`** — a previous worker died
  mid-run; the reaper has freed the queue. Resubmit.
- **Job `failed` mentioning missing data file** — populate `data/` with the
  required CSVs / models / geojson. The simulator can't generate inputs.
- **Connection refused to OSRM** — `OSRM_HOST`/`OSRM_PORT` in `.env` don't match
  where OSRM is actually running.
