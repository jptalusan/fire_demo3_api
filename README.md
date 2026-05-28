# fire_demo3_api_v2

Fire simulator backend, restructured to match the industry-standard layout used by
the EmergencyResponse-gym `develop` branch. Same simulator engine and route surface
as `fire_demo3_api`, wrapped in auth + DB-backed job queue + worker.

## Layout

```
src/
  backend/        FastAPI app: config, routes, schemas, services
    routes/       auth, jobs, engine, incidents, stations, system
    schemas/      pydantic models (auth, engine, incidents, sim)
    services/     auth (bcrypt+jwt), simulator (abstract + C++ subprocess impl)
  db/             SQLAlchemy ORM, session, crud, local storage
  engine/         Ported simulation logic (run_simulation_internal etc.)
  core/           Path constants
  worker/         Job-queue worker process
tests/
  unit/  integration/  e2e/
configs/          YAML/JSON simulator configs
storage/          SQLite DB + per-job artifact dirs
data/             Static inputs (incidents, stations, models, geojson)
logs/             Simulator run logs (gitignored)
```

## Key differences vs. fire_demo3_api

| Concern | fire_demo3_api | fire_demo3_api_v2 |
|---|---|---|
| Persistence | Files only | SQLite + files |
| Auth | None | JWT + bcrypt |
| Job model | Sync `await` in request | DB job row, worker picks up |
| Simulator coupling | Inline subprocess call | `Simulator` ABC; `CppSubprocessSimulator` impl |
| Tests | Single notebook | `tests/{unit,integration,e2e}` |
| Deploy | Manual uvicorn | `docker-compose` (backend + worker + OSRM) |

## Quickstart (local, no Docker)

```bash
cp .env.example .env
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# place data/ assets (copy from fire_demo3_api/data) and the compiled binary at data/fire_simulator
uvicorn backend.main:app --reload &
python -m worker.main &
```

## Quickstart (Docker)

```bash
cp .env.example .env
docker compose up --build
```

## Auth flow

```
POST /auth/register   {username, password}
POST /auth/login      {username, password}      -> token (cookie + body)
POST /jobs            SimJobPayload             (Bearer)
GET  /jobs                                      (Bearer)
GET  /jobs/{job_id}                             (Bearer)
```

Engine routes (`/engine/run-simulation`, `/engine/run-comparison`) are preserved as
**synchronous** endpoints for backwards compatibility; queued mode lives under `/jobs`.

## Tests

```bash
pytest -q                       # everything
pytest tests/unit -q            # fast
pytest -m "not slow"
```
