# fire_demo3_api_v2 — API Reference

Complete reference for the backend API: endpoints, auth, the **job model**, and the
full **payload / result schemas** for `run-simulation` and `run-comparison` (which the
auto-generated OpenAPI can't fully express because the job payload is a free-form object).

- Base URL (dev): `http://127.0.0.1:8123`
- Interactive docs: `/docs` (Swagger) · `/redoc` · raw spec `/api/v1/openapi.json`
- Auth: HttpOnly cookie set by `POST /auth/login`, sent automatically (same-site).

---

## 1. Concepts

### Auth
Cookie-based JWT, **6-hour** expiry. Log in once; the browser carries the cookie on every
request. Any endpoint can return **401** when the session is missing/expired — treat that
as "re-login". Bearer also works: `Authorization: Bearer <access_token>` from the login body.

### The job model (how simulations run)
Simulations are **asynchronous**. You don't get results from one call:

```
POST /api/jobs            -> { id, status: "pending", ... }     (returns instantly)
        │
        ▼  a background worker claims it
   status: pending -> running -> done | failed
        │
GET /api/jobs/{id}/progress  -> live incidents processed / total   (while running)
GET /api/jobs/{id}           -> full job; `result` populated when status="done"
```

- **One worker** processes jobs in priority/created order; multiple workers scale it.
- **Per-job timeout**: a run is cancelled after `JOB_TIMEOUT_SEC` (default **3600s**) and
  marked `failed` — protects against non-terminating configs.
- Jobs **persist**: payload, result, duration, timestamps. A page refresh loses nothing.

### Status lifecycle
| status | meaning | fields set |
|---|---|---|
| `pending` | queued, not started | `queue_position` |
| `running` | worker executing | `started_at` |
| `done` | finished OK | `result`, `finished_at`, `duration_seconds` |
| `failed` | errored / timed out | `error`, `finished_at` |

---

## 2. Endpoint summary

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | no | Liveness |
| GET | `/version` | no | Name + version |
| POST | `/auth/register` | no | Create account |
| POST | `/auth/login` | no | Log in (sets cookie) |
| GET | `/auth/me` | yes | Current user / session check |
| POST | `/auth/logout` | yes | Clear cookie |
| POST | `/api/jobs` | yes | **Submit a simulation job** |
| GET | `/api/jobs` | yes | List your jobs |
| GET | `/api/jobs/{id}` | yes | One job (+ result) |
| GET | `/api/jobs/{id}/progress` | yes | Live progress |
| GET | `/api/jobs/queue/status` | yes | Queue snapshot |
| POST | `/api/incidents/get-incidents` | yes | Historical incidents (CSV) |
| POST | `/api/incidents/generate-incidents` | yes | Synthetic incidents (CSV) |
| POST | `/api/incidents/process-incidents` | yes | Stats for a CSV |
| GET | `/api/stations/get-stations` | yes | List station CSVs |
| GET | `/api/stations/get-shapes` | yes | List GeoJSON overlays |

---

## 3. Auth endpoints

### POST /auth/register
Request `{ "username": "alice", "password": "hunter2" }`.

| Parameter | Type | Required | Accepts |
|---|---|---|---|
| `username` | string | **yes** | 3–64 characters, unique |
| `password` | string | **yes** | 6–128 characters |

Response `201 { "id": 1, "username": "alice" }` · `409` if taken · `422` on validation.

### POST /auth/login
Request `{ "username": "alice", "password": "hunter2" }`.

| Parameter | Type | Required | Accepts |
|---|---|---|---|
| `username` | string | **yes** | an existing username |
| `password` | string | **yes** | the matching password |

Response `200 { "access_token": "<jwt>", "token_type": "bearer" }` and sets
`Set-Cookie: auth_token=…; HttpOnly; SameSite=Lax; Max-Age=21600`. `401` on bad creds.

### GET /auth/me
Response `200 { "id": 1, "username": "alice" }` · `401` if no/expired session.
Use on app load to decide login-gate vs app.

### POST /auth/logout
Response `200 { "status": "ok" }`, clears the cookie.

---

## 4. Jobs — the core

### POST /api/jobs — submit a simulation

**Request body**
```jsonc
{
  "kind": "run-simulation" | "run-comparison",
  "payload": { /* SimConfig (run-simulation) or {baseline, newConfig} (run-comparison) */ },
  "priority": 0   // higher runs first
}
```

**Response `201`** — a `JobResponse` (see §5) with `status: "pending"` and `queue_position`.

#### Payload for `run-simulation` — a `SimConfig`
```jsonc
{
  "models": {
    "incident":   "historical_incidents",  // | "synthetic_incidents"
    "travelTime": "OSRM",                   // | "ARCGIS" (->OSRM) | "INTERPOLATED"
    "serviceTime":"ml_based"                // | "constant" | "empirical_servicetimes"
  },
  "date_range": { "start_date": "2024-06-01", "end_date": "2024-06-03" },
  "incident_type": "ems_fire",              // | "fire"
  "dispatch_policy": "nearest",             // | "firebeats"
  "station_data": "default_stations",       // | "custom_stations" | "optimized_stations"
  "disable_ems": false,                     // true = fire-only
  "stations": null                          // only for custom_stations (see below)
}
```

#### Payload for `run-comparison`
```jsonc
{
  "baseline":  { /* SimConfig — usually default_stations */ },
  "newConfig": { /* SimConfig — the change to evaluate */ }
}
```
Both run in parallel; the result includes baseline, newConfig, and a per-metric diff.

#### Custom stations (`station_data: "custom_stations"`)
Provide a `stations` array. Each station:
```jsonc
{
  "id": "0",
  "name": "Station 01",
  "lat": 36.2293898,
  "lon": -86.75674762,
  "apparatus": [
    { "type": "Engine", "count": 1 },
    { "type": "Medic",  "count": 1 }
  ]
}
```
Apparatus `type` ∈ `Engine, Truck, Rescue, Hazard, Squad, FAST, Medic, Brush, Boat, UTV, REACH, Chief`.

> ⚠️ **Resolvability rule.** Every incident type must have apparatus that can serve it —
> fire incidents need an **Engine**, EMS need a **Medic**. A layout missing them (e.g. 0
> engines for an `ems_fire` run) makes the simulation **never terminate**; it will run to
> the timeout and fail. Validate this client-side before submitting.

#### Enum reference
| Field | Allowed values |
|---|---|
| `kind` | `run-simulation`, `run-comparison` |
| `models.incident` | `historical_incidents`, `synthetic_incidents` |
| `models.travelTime` | `OSRM`, `ARCGIS`, `INTERPOLATED` |
| `models.serviceTime` | `ml_based`, `constant`, `empirical_servicetimes` |
| `incident_type` | `fire`, `ems_fire` |
| `dispatch_policy` | `firebeats`, `nearest` |
| `station_data` | `default_stations`, `custom_stations`, `optimized_stations` |
| apparatus `type` | `Engine, Truck, Rescue, Hazard, Squad, FAST, Medic, Brush, Boat, UTV, REACH, Chief` |

#### Parameter dictionary — every field, what it accepts

**`JobSubmitRequest`** (top-level request body)

| Parameter | Type | Required | Default | Accepts |
|---|---|---|---|---|
| `kind` | string | no | `"run-simulation"` | `run-simulation`, `run-comparison` |
| `payload` | object | **yes** | — | a `SimConfig` (run-simulation) **or** `{ "baseline": SimConfig, "newConfig": SimConfig }` (run-comparison) |
| `priority` | integer | no | `0` | any integer; higher numbers are dequeued first |

**`SimConfig`** (the `payload` for run-simulation; each side of a comparison)

| Parameter | Type | Required | Default | Accepts |
|---|---|---|---|---|
| `models` | object | **yes** | — | the `models` object below |
| `date_range` | object | **yes** | — | the `date_range` object below |
| `incident_type` | string | **yes** | — | `fire`, `ems_fire` |
| `dispatch_policy` | string | no | `nearest` | `firebeats`, `nearest` |
| `station_data` | string | no | `default_stations` | `default_stations`, `custom_stations`, `optimized_stations` |
| `disable_ems` | boolean | no | `false` | `true` (fire-only), `false` (include EMS) |
| `stations` | array&lt;Station&gt; \| null | conditional | `null` | required when `station_data="custom_stations"`; otherwise omit/null |

**`models`**

| Parameter | Type | Required | Default | Accepts |
|---|---|---|---|---|
| `incident` | string | **yes** | — | `historical_incidents` (replay real incidents in range), `synthetic_incidents` (generate) |
| `travelTime` | string | no | `OSRM` | `OSRM`, `ARCGIS` (treated as OSRM), `INTERPOLATED` |
| `serviceTime` | string | no | `ml_based` | `ml_based`, `constant`, `empirical_servicetimes` |

**`date_range`**

| Parameter | Type | Required | Default | Accepts |
|---|---|---|---|---|
| `start_date` | string | **yes** | — | `YYYY-MM-DD` or ISO‑8601 timestamp (e.g. `2024-06-01` or `2024-06-01T05:00:00.000Z`); only the date part is used |
| `end_date` | string | **yes** | — | same formats; inclusive end of window |

**`Station`** (each item of `stations`)

| Parameter | Type | Required | Default | Accepts |
|---|---|---|---|---|
| `id` | string | **yes** | — | unique id, e.g. `"0"`…`"39"` |
| `name` | string | **yes** | — | free text, e.g. `"Station 01"` |
| `lat` | number | **yes** | — | WGS84 latitude (Nashville ≈ `35.8`–`36.5`) |
| `lon` | number | **yes** | — | WGS84 longitude (Nashville ≈ `-87.1`–`-86.4`) |
| `apparatus` | array&lt;Apparatus&gt; | no | `[]` | list of apparatus entries below |

**`Apparatus`** (each item of a station's `apparatus`)

| Parameter | Type | Required | Default | Accepts |
|---|---|---|---|---|
| `type` | string | **yes** | — | `Engine`, `Truck`, `Rescue`, `Hazard`, `Squad`, `FAST`, `Medic`, `Brush`, `Boat`, `UTV`, `REACH`, `Chief` |
| `count` | integer | **yes** | — | `≥ 0` |

> Resolvability: an `ems_fire` run must have at least one `Engine` (fire) and one `Medic`
> (EMS) reachable across the layout, or the simulation won't terminate.

### GET /api/jobs
List your jobs (newest first). Array of `JobResponse`. Pending jobs include `queue_position`.

### GET /api/jobs/{id}
One `JobResponse`. `result` is the full simulation output once `status="done"`. `404` if
the job doesn't exist or isn't yours.

### GET /api/jobs/{id}/progress
```jsonc
{
  "job_id": 42, "status": "running",
  "processed": 470, "total": 810, "percent": 58.0,
  "legs": { "simulation": { "processed": 470, "total": 810 } }
  // comparison: { "baseline": {...}, "newConfig": {...} }
}
```
Counts incidents *reported* (fills early); `status` is the source of truth for completion.

### GET /api/jobs/queue/status
```jsonc
{ "pending_total": 2, "running_total": 1, "your_pending": 1, "your_running": 0, "your_next_position": 1 }
```

---

## 5. Schemas

### JobResponse
```jsonc
{
  "id": 42,
  "user_id": 1,
  "kind": "run-simulation",
  "status": "done",
  "payload": { /* the SimConfig or {baseline,newConfig} you submitted */ },
  "result":  { /* SimulationResult or ComparisonResult — see below; null until done */ },
  "error":   null,                 // string when failed
  "attempts": 1,
  "created_at":  "2026-05-26T20:18:00",
  "started_at":  "2026-05-26T20:18:59",
  "finished_at": "2026-05-26T20:19:37",
  "duration_seconds": 38.16,       // null until terminal
  "queue_position": null           // 1-based when pending
}
```

### SimulationResult (`result` for run-simulation, and each leg of a comparison)
```jsonc
{
  "status": "success",
  "total_incidents": 810,
  "average_response_time": 264.06,          // seconds
  "coverage_percent": 72.84,
  "P90_continuous": 446.2,                  // seconds
  "duration_seconds": 38.16,
  "station_report": [
    { "Station 01": {
        "travel_time_mean": 218.4,
        "incident_count": 23,
        "travel_times": [225.1, 185.3, ...],          // per-incident, seconds
        "incident_locations": [[36.24,-86.75], ...]   // [lat,lon]
    } }
    // one object per station (~40)
  ],
  "vehicle_report": [ { /* per-apparatus metrics, keyed by type */ } ],
  "average_response_time_per_incident_type": [
    { "incident_type": "Medical", "incident_count": 640, "average_travel_time": 252.4 }
  ]
  // when station_data=default_stations & historical: also an "evaluation" block
  // comparing simulated vs actual response times.
}
```

### ComparisonResult (`result` for run-comparison)
```jsonc
{
  "status": "success",
  "baseline":  { /* SimulationResult */ },
  "newConfig": { /* SimulationResult */ },
  "comparison": {
    "overall_metrics": {
      "average_response_time": { "baseline": 266.05, "new": 261.27,
                                 "difference": -4.78, "percent_change": -1.80, "improved": true },
      "coverage_percent":      { "baseline": 72.10, "new": 74.20, "difference": 2.10, "improved": true },
      "p90_response_time":     { "baseline": 450.2, "new": 446.2, "difference": -4.00, "improved": true }
    },
    "station_comparison": [
      { "station_id": "...", "station_name": "Station 01",
        "total_incidents": { "baseline": 24, "new": 24, "difference": 0 },
        "average_travel_time": { "baseline": 239.3, "new": 234.1, "difference": -5.2, "improved": true },
        "p90_travel_time": { "baseline": 365.1, "new": 360.0, "difference": -5.1, "improved": true },
        "status": "existing_station" | "new_station" | "removed_station" }
    ],
    "incident_type_comparison": [
      { "incident_type": "Medical",
        "incident_count": { "baseline": 640, "new": 640, "difference": 0 },
        "average_travel_time": { "baseline": 252.4, "new": 248.1,
                                 "difference": -4.3, "percent_change": -1.7, "improved": true } }
    ],
    "improvements": {
      "response_time_improved": true, "coverage_improved": true, "p90_improved": true,
      "stations_with_better_response": 27, "stations_with_worse_response": 8,
      "new_stations_added": 0, "stations_removed": 0
    },
    "summary": {
      "overall_assessment": "improved" | "degraded" | "mixed",
      "key_findings": [ "Average response time improved by 4.78 seconds (1.8%)", ... ]
    }
  }
}
```

---

## 6. Incidents

### POST /api/incidents/get-incidents — historical (CSV out)
```jsonc
{ "model_id": "historical_incidents",
  "filters": { "date_range": { "start": "2024-06-01", "end": "2024-06-03" },
               "incident_type": "ems_fire" } }
```
| Parameter | Type | Required | Accepts |
|---|---|---|---|
| `model_id` | string | **yes** | `historical_incidents` (only supported value) |
| `filters.date_range.start` | string | **yes** | `YYYY-MM-DD` |
| `filters.date_range.end` | string | **yes** | `YYYY-MM-DD` |
| `filters.incident_type` | string | **yes** | `fire`, `ems_fire` |

**Response**: `text/csv` — columns `incident_id,lat,lon,incident_type,incident_level,datetime,category`.
`400` if range missing / unsupported model.

### POST /api/incidents/generate-incidents — synthetic (CSV out)
```jsonc
{ "date_range": { "start": "2024-06-01", "end": "2024-06-03" },
  "incident_type": "ems_fire", "model": "growth_v1", "seed": 42 }
```
| Parameter | Type | Required | Default | Accepts |
|---|---|---|---|---|
| `date_range.start` | string | **yes** | — | `YYYY-MM-DD` |
| `date_range.end` | string | **yes** | — | `YYYY-MM-DD` |
| `incident_type` | string | **yes** | — | `fire`, `ems_fire` |
| `model` | string | no | `growth_v1` | `growth_v1`, `default` |
| `seed` | integer | no | `42` | any integer (fixes the random draw) |

**Response**: `text/csv`, same columns. Cached per (model, dates, seed).

### POST /api/incidents/process-incidents — stats
**Request**: raw CSV body (`Content-Type: text/csv`).

| Input | Type | Required | Accepts |
|---|---|---|---|
| body | CSV text | **yes** | must include columns `incident_type` and `datetime`; other columns ignored |

**Response**:
```jsonc
{ "status": "success", "total_incidents": 810,
  "incident_counts": { "Medical": 640, "Building fire": 22 },
  "average_time_between_incidents_minutes": 5.34 }
```

---

## 7. Stations / shapes

### GET /api/stations/get-stations
`{ "stations": ["stations_with_apparatus.csv", "stations.csv", ...] }`

### GET /api/stations/get-shapes
`{ "shapes": ["beats_shpfile.geojson", "bounds.geojson", ...] }`

---

## 8. System

`GET /health` → `{ "status": "ok" }` · `GET /version` → `{ "name": "fire_demo3_api_v2", "version": "0.1.0" }`.

---

## 9. Errors

| Code | When | Body |
|---|---|---|
| 401 | missing/expired session | `{ "detail": "Missing authorization header or auth cookie" }` / `"Invalid token"` |
| 404 | job not found / not yours | `{ "detail": "Job not found" }` |
| 409 | username exists | `{ "detail": "User already exists" }` |
| 422 | request validation | `{ "detail": [ { "loc": [...], "msg": "...", "type": "..." } ] }` |
| 400 | bad incidents request | `{ "detail": "..." }` |

A **failed job** is not an HTTP error — it's `200` with `status: "failed"` and an `error`
string (e.g. timeout / unresolvable-config message).

---

## 10. End-to-end example (cURL)

```bash
BASE=http://127.0.0.1:8123
# 1. login (store cookie)
curl -s -c cookies.txt -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"hunter2"}'

# 2. submit a run-simulation job
JID=$(curl -s -b cookies.txt -X POST $BASE/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"kind":"run-simulation","payload":{
        "models":{"incident":"historical_incidents","travelTime":"OSRM","serviceTime":"ml_based"},
        "date_range":{"start_date":"2024-06-01","end_date":"2024-06-03"},
        "incident_type":"ems_fire","dispatch_policy":"nearest",
        "station_data":"default_stations","disable_ems":false}}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# 3. poll progress, then fetch the result
curl -s -b cookies.txt $BASE/api/jobs/$JID/progress
curl -s -b cookies.txt $BASE/api/jobs/$JID      # status -> done, result populated
```

---

## 11. Typical frontend sequence

```
GET  /auth/me                         -> logged in? else show login
GET  /api/stations/get-stations       -> populate dropdowns
GET  /api/stations/get-shapes
POST /api/incidents/get-incidents      -> preview incidents on the map
POST /api/jobs {kind, payload}         -> get job id
loop GET /api/jobs/{id}/progress       -> progress bar
     GET /api/jobs/{id}                -> until status=done -> render result
GET  /api/jobs  +  /api/jobs/queue/status   -> history + queue badge (background poll)
```
