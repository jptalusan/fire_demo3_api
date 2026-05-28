# fire_demo3_api

FastAPI backend for the fire/EMS dispatch simulator. Cookie-based JWT auth,
SQLite-backed job queue, and a background worker that drives the C++ simulator.

Full API contract: [`API_REFERENCE.md`](./API_REFERENCE.md).

---

## Prerequisites

- **Python 3.10+** (tested on 3.10 and 3.11)
- The compiled C++ simulator binary at `data/fire_simulator` (executable; not in this repo)
- The data assets under `data/` (incidents, stations, ONNX models, interpolation matrices, `ems_stats`, geojson). Easiest source: copy `data/` from a working simulator install.
- A reachable **OSRM** service (the bundled `docker-compose.yml` runs one on host port `8080`)
- Optional: **Node 18+** and `npm` if you want to run the React frontend

---

## Layout

```
src/
  backend/        FastAPI app
    main.py       app + startup hook
    config.py     env-driven Settings; ensure_runtime_dirs()
    routes/       auth, jobs, incidents, stations, system
    schemas/      pydantic models (auth, sim, incidents)
    services/     auth (bcrypt + JWT), simulator (ABC + C++ subprocess impl)
  db/             SQLAlchemy ORM, session, crud, local storage
  engine/         Wraps the C++ simulator and parses results
  core/           Path constants
  worker/         Polls the DB for pending jobs and runs them
tests/            unit / integration / e2e   (121 tests)
storage/          SQLite DB + per-job artifact dirs   (gitignored)
data/             Static inputs                       (gitignored)
logs/             Per-run simulator output            (gitignored)
frontend/         Vite + React UI (optional)
```

`storage/`, `logs/`, and `data/` are created automatically on first startup if missing — you only need to populate `data/` with the simulator's input files.

---

## Quickstart (local, no Docker)

```bash
# 1. clone
git clone -b backend-v2 https://github.com/jptalusan/fire_demo3_api.git
cd fire_demo3_api

# 2. env (edit SECRET_KEY for anything beyond dev)
cp .env.example .env

# 3. virtualenv + install
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # uv pip install -e ".[dev]" also works

# 4. put your data assets in data/  (see "Required data files" below)

# 5. start the API on port 8000 (any port works)
uvicorn backend.main:app --port 8000

# 6. in a second terminal, start the worker
source .venv/bin/activate
python -m worker.main
```

Verify:

```bash
curl http://localhost:8000/health        # {"status":"ok"}
open  http://localhost:8000/docs         # interactive Swagger UI
```

---

## Quickstart (Docker)

```bash
cp .env.example .env
docker compose up --build
```

Starts three services:

| Service | Host port | What |
|---|---|---|
| `backend` | 8000 | FastAPI app |
| `worker`  | — | Job runner (no exposed port) |
| `osrm`    | 8080 | OSRM routing service |

Host directories mounted into the containers: `./data` (ro), `./storage`, `./logs`. Put your data files in `./data` before `docker compose up`.

---

## Frontend (optional)

```bash
cd frontend
npm install
npm run dev        # vite dev server, http://localhost:5173
```

The frontend hits the backend at the same host on port `8000` by default. Override with `VITE_API_BASE` if needed.

---

## `.env` reference

```
DATABASE_URL=sqlite:///./storage/app.db        # SQLite file path
SECRET_KEY=dev-secret-change-me                # JWT signing key (change in prod)
MAX_ATTEMPTS=5                                 # login attempt cap (advisory)
STORAGE_ROOT=./storage                         # per-job artifact root
OSRM_HOST=localhost                            # OSRM service host
OSRM_PORT=8080                                 # OSRM service port
SIMULATOR_BINARY=./data/fire_simulator         # path to the C++ binary
```

`JOB_TIMEOUT_SEC` (default `3600`) caps how long a single job may run; the worker fails any job that exceeds it.

---

## Required data files (`data/`)

These come from your simulator install — drop them into `./data/`:

| Path | What |
|---|---|
| `data/fire_simulator` | the compiled C++ binary (must be executable) |
| `data/incidents.csv`, `data/incidents_small.csv` | base/fallback incident inputs |
| `data/incident_resolution_times.csv`, `…_fire.csv` | historical incidents (2022–2025) used by `historical_incidents` model |
| `data/stations_with_apparatus.csv`, `data/stations.csv` | default station roster |
| `data/models/*.onnx`, `…features_mapping.json` | service-time ML model + EMS variant |
| `data/interpolation_data/*.json`, `data/interpolation_fire/*.json` | zone travel-time matrices |
| `data/ems_stats/*.csv` | scene-time, hospital, and transport tables |
| `data/bounds.geojson`, `beats_shpfile*.geojson`, `zones.csv`, `NFDResponse.csv`, `response_time_summary2.csv` | geography + reference tables |

The simulator will fail with a clear "file not found" message if any of these are missing.

---

## Using the API

All `/api/*` endpoints require a session cookie set by `POST /auth/login`.

```bash
B=http://localhost:8000

# create an account
curl -X POST $B/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"hunter2"}'

# log in (stores cookie)
curl -c cookies.txt -X POST $B/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"hunter2"}'

# submit a simulation job
curl -b cookies.txt -X POST $B/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"kind":"run-simulation","payload":{
        "models":{"incident":"historical_incidents","travelTime":"OSRM","serviceTime":"ml_based"},
        "date_range":{"start_date":"2024-06-01","end_date":"2024-06-03"},
        "incident_type":"ems_fire",
        "dispatch_policy":"nearest",
        "station_data":"default_stations",
        "disable_ems":false}}'

# poll the job
curl -b cookies.txt $B/api/jobs/1
curl -b cookies.txt $B/api/jobs/1/progress
```

Job status moves: `pending → running → done | failed`. `result` is populated when `status="done"`; `error` is populated when `status="failed"`. See `API_REFERENCE.md` for every endpoint, payload field, and the full result schema.

---

## Tests

```bash
PYTHONPATH=src DATABASE_URL=sqlite:///:memory: SECRET_KEY=test STORAGE_ROOT=/tmp/fd3_test \
  pytest tests/ -q
```

121 tests, ~15 s. Uses an in-memory SQLite DB and a fake `Simulator`, so it never invokes the real C++ binary or OSRM.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Job stays pending forever` | Worker isn't running | Start `python -m worker.main` |
| `Job failed: No such file or directory: '.../data/...'` | Required data file missing | Drop the file into `data/` (see table above) |
| `Connection refused to OSRM` | OSRM not running or wrong port | Start OSRM; align `OSRM_HOST` / `OSRM_PORT` in `.env` |
| `Job failed: Orphaned: no live worker` | A previous worker crashed mid-run | The reaper has freed the queue; resubmit |
| `Job failed: ... exceeded the 3600s limit` | Configuration that can't terminate (e.g. fire incidents with no `Engine` apparatus) | Fix the config; submit again |
| `401 Missing authorization header or auth cookie` | Session expired (cookie TTL is 6 h) | Log in again |
| `register → 409 User already exists` | Username taken | Pick a different username or log in |
