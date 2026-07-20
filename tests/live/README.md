# Live-integration tests (`tests/live`)

Exercises a **running backend** end-to-end. Every test hits the real HTTP
surface — auth, stations, incidents, jobs, simulations, comparisons —
and skips itself cleanly if the server isn't reachable, so it's safe to
have in the same tree as unit/regression suites.

## Run against a stack

```bash
# Local docker (default)
pytest tests/live -v

# Any URL, including the deployed /v3/ or /v2/
LIVE_BASE_URL=https://hobvmisap57.nashville.org/v3 pytest tests/live -v

# Skip everything (the fast unit run)
pytest --ignore=tests/live
```

## What it covers

| File | Scope |
|---|---|
| `test_health.py` | `/health`, `/version`, OpenAPI spec discoverability |
| `test_auth.py` | portal-login, register (idempotent), login, /me, logout, bearer + cookie paths |
| `test_stations.py` | roster (verifies `Suppression_Chief` + `EMS_Chief` land), get-stations, get-shapes, path-traversal rejection |
| `test_incidents.py` | historical get + process, generate-incidents (`optional` — skipped if the growth bundle isn't present) |
| `test_jobs_simulation.py` | Submit a 3-day historical sim → poll to `done` → sanity-check `total_incidents`/`avg`/`P90` |
| `test_jobs_comparison.py` | NEAREST vs FIREBEATS comparison → poll → both sides succeed → `comparison` block present |
| `test_container_state.py` | Optional `docker exec`-based checks: bind-mount inode match, OSRM reachable from inside container, binary + data alignment. Skipped if the docker CLI isn't available or `LIVE_CONTAINER_NAME` isn't set. |

## Config knobs (env vars)

| Var | Default | Meaning |
|---|---|---|
| `LIVE_BASE_URL` | `http://localhost:8000` | Root URL of the API. No trailing slash. |
| `LIVE_USERNAME` | `livetest` | Username used with portal-login/register/login. |
| `LIVE_PASSWORD` | `livetest-password-123` | Password used with register/login. Must be ≥ 6 chars. |
| `LIVE_SIM_START` | `2024-03-01` | Historical window start (YYYY-MM-DD). |
| `LIVE_SIM_END` | `2024-03-03` | Historical window end. Short window keeps the job under a minute. |
| `LIVE_INCIDENT_TYPE` | `ems_fire` | Or `fire`. |
| `LIVE_JOB_TIMEOUT_S` | `600` | Max seconds to wait for a submitted job to reach `done` / `failed`. |
| `LIVE_CONTAINER_NAME` | *(unset)* | If set (e.g. `fire_demo3_v3_backend`), `test_container_state.py` runs `docker exec` sanity checks. |
| `LIVE_HOST_DATA_DIR` | *(unset)* | Host-side `./data` to compare inodes against the container. Only used by `test_container_state.py`. |

## Failure semantics

- Any test failure → the suite exits non-zero and prints a targeted
  message. No generic "assertion failed" walls; each test hand-writes
  the operator hint (which file, which command, which value).
- Any *unreachable-server* → the whole suite is skipped, not failed. That
  way `pytest tests/` works fine even when nothing is running.
