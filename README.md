# fire_demo3_api

FastAPI backend for the fire/EMS dispatch simulator. Cookie-based JWT auth,
SQLite-backed job queue, and a background worker that drives the C++ simulator.

### Documentation

| Doc | When to open it |
|---|---|
| **[`FRONTEND_GUIDE.md`](./FRONTEND_GUIDE.md)** | You're writing a frontend against this API — landing page with every knob and link |
| [`API_REFERENCE.md`](./API_REFERENCE.md) | Field-by-field endpoint reference (all enums, payload + result shapes) |
| [`DEMO.pdf`](./DEMO.pdf) | Slide deck — architecture, lifecycle, payload examples, run commands |
| `/docs` on a running backend | Interactive Swagger UI to try endpoints in the browser |
| `/api/v1/openapi.json` on a running backend | Raw spec for client generation (`openapi-typescript`, Postman) |

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

# 5. start the API (port comes from .env — change BACKEND_PORT if you like)
uvicorn backend.main:app --host 0.0.0.0 --port ${BACKEND_PORT:-8000}

# 6. in a second terminal, start the worker
source .venv/bin/activate
python -m worker.main
```

Verify (substitute your `$BACKEND_PORT`):

```bash
curl http://localhost:${BACKEND_PORT:-8000}/health    # {"status":"ok"}
open  http://localhost:${BACKEND_PORT:-8000}/docs     # interactive Swagger UI
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

## Frontend on a different domain

If your frontend lives on a different origin than the API (e.g. `https://app.example.com` and `https://api.example.com`), set these in the backend's `.env`:

```
CORS_ALLOWED_ORIGINS=https://app.example.com,https://staging.example.com
COOKIE_SAMESITE=none        # required for cross-site cookies
COOKIE_SECURE=true          # required when SameSite=None; needs HTTPS
```

Frontend side: build with `VITE_API_BASE=https://api.example.com` and use `fetch(..., {credentials: "include"})`. Backend MUST be served over HTTPS for the `Secure` cookie to be accepted.

Skip cookies entirely if you prefer: set `Authorization: Bearer <access_token>` (from `/auth/login`) on every call; only `CORS_ALLOWED_ORIGINS` then needs to include the frontend origin.

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
B=http://localhost:${BACKEND_PORT:-8000}

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
