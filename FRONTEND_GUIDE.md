# Frontend Developer Guide

Everything a frontend developer needs to build against this API: where the docs
live, which knobs to turn, what to call, and where things break.

---

## Where to look

| Doc | What's in it |
|---|---|
| [`README.md`](./README.md) | Setup, prerequisites, run commands, troubleshooting |
| [`API_REFERENCE.md`](./API_REFERENCE.md) | **Every endpoint, every field, every enum, full request/response schemas** |
| [`DEMO.pdf`](./DEMO.pdf) | Slide deck — architecture, lifecycle, payload shapes, run commands |
| [`DEMO.tex`](./DEMO.tex) | Source for the slides (rebuild with `xelatex DEMO.tex`) |
| `/docs` (live, on a running backend) | Interactive Swagger UI — try endpoints in the browser |
| `/redoc` (live) | Static reference rendering of the OpenAPI spec |
| `/api/v1/openapi.json` (live) | Raw OpenAPI 3.1 spec — feed to `openapi-typescript` for a typed client |

If you only read one thing, read `API_REFERENCE.md`. If you only run one thing, hit `/docs`.

---

## Knobs you might want to change

All knobs live in **`.env`** at the repo root. No source code edits required.

### Ports
| Var | Default | What it controls |
|---|---|---|
| `BACKEND_PORT` | `8000` | uvicorn HTTP port; also used by `docker-compose` for the host mapping |
| `VITE_PORT` | `5173` | Vite dev server port |
| `VITE_API_TARGET` | `http://localhost:8000` | Where the Vite proxy forwards `/api` and `/auth` calls; must point at `BACKEND_PORT` |
| `OSRM_PORT` | `8080` | OSRM port the backend talks to |
| `OSRM_HOST_PORT` | `8080` | Host port for OSRM under docker-compose |

### Frontend → backend URL
| Var | Default | What it controls |
|---|---|---|
| `VITE_API_BASE` | (empty → relative URLs through the Vite proxy) | If set, frontend talks to this absolute URL instead of `/api`. Use it when FE and BE live on different origins (e.g. `VITE_API_BASE=https://api.example.com`). |

### Auth & cross-origin
| Var | Default | What it controls |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-me` | JWT signing key. Set to a long random string in prod. |
| `CORS_ALLOWED_ORIGINS` | dev defaults (`localhost:3000,5173,8000` + `127.0.0.1` variants) | Comma-separated list of FE origins allowed to call the API. **Add your FE origin here when it's on a different host.** |
| `COOKIE_SAMESITE` | `lax` | Auth cookie SameSite. Set to `none` for cross-site (different domain) frontends. |
| `COOKIE_SECURE` | auto-`true` when `SameSite=none`, else `false` | HTTPS-only cookie. Required by browsers when `SameSite=None`. |

### Misc
| Var | Default | What it controls |
|---|---|---|
| `JOB_TIMEOUT_SEC` | `3600` | Worker cancels and fails a job that runs longer |
| `MAX_ATTEMPTS` | `5` | Job retry cap (advisory; no auto-retry today) |
| `DATABASE_URL` | `sqlite:///./storage/app.db` | SQLite path; swap for Postgres URL in prod |
| `STORAGE_ROOT` | `./storage` | Per-job artifact directory root |

---

## The contract you'll be coding against

Three things to internalize:

1. **Log in once, send the cookie (or bearer) on every call.**
2. **Long work goes through `/api/jobs`. Submit, then poll.**
3. **`run-simulation` and `run-comparison` use the same submit endpoint with different payloads.**

### Auth, in 4 calls
```
POST /auth/register   {username, password}        → 201
POST /auth/login      {username, password}        → 200 + cookie + access_token
GET  /auth/me                                     → 200 {id, username}      (sanity)
POST /auth/logout                                 → clears cookie
```

### A job, in 3 calls
```
POST /api/jobs        {kind, payload, priority}   → {id, status:"pending"}
GET  /api/jobs/{id}/progress                      → {processed, total, percent}     (poll ~3s)
GET  /api/jobs/{id}                               → status moves to "done"|"failed"
```

`payload` shape depends on `kind`:

| kind | payload |
|---|---|
| `run-simulation` | a single `SimConfig` (see `API_REFERENCE.md` §4) |
| `run-comparison` | `{baseline: SimConfig, newConfig: SimConfig}` — both run in parallel; result includes a diff |

Full field-by-field schema with every enum (`incident_type`, `dispatch_policy`, `station_data`, apparatus `type`, etc.) is in `API_REFERENCE.md`.

---

## Where things differ between dev and prod

| Concern | Dev (Vite proxy) | Prod (different domains) |
|---|---|---|
| API base in JS | `''` (relative) | `VITE_API_BASE=https://api.example.com` |
| CORS | dev defaults cover localhost | `CORS_ALLOWED_ORIGINS=https://app.example.com` |
| Cookie SameSite | `lax` | `none` (cross-site) |
| Cookie Secure | `false` (HTTP localhost) | `true` (HTTPS required) |
| FE fetch | normal | `credentials: 'include'` (already in code) |

The README's "Frontend on a different domain" section has the exact `.env` block for prod.

---

## Where to wire in your own UI

Three places matter; everything else is one of them:

| You want to… | Touch |
|---|---|
| Make an authenticated request | `services/api.ts::apiFetch` — single wrapper, sets `credentials:'include'` and surfaces 401 globally |
| Submit / poll a job | `services/jobs.ts::runJob` (one-shot) or `services/jobs.ts::submitJob` + `getJob` + `getJobProgress` (custom polling) |
| Read the current user / log out | `context/AuthContext.tsx::useAuth()` (returns `{user, login, logout, loading}`) |

A page refresh keeps the user logged in (cookie) **and** preserves any in-flight jobs (DB-persisted). The Jobs tab demonstrates resuming after a refresh.

---

## Common surprises (and the fix)

| You see | Why | Fix |
|---|---|---|
| `401 Missing authorization header or auth cookie` on every call from your SPA | Cross-origin without `credentials:'include'`, or backend CORS doesn't list your FE origin | Add origin to `CORS_ALLOWED_ORIGINS`; set `fetch(..., {credentials: 'include'})` |
| Login returns `200` + cookie, but next call is `401` | Cookie SameSite/Secure mismatch (cross-site needs `none` + `secure`) | Set `COOKIE_SAMESITE=none`, `COOKIE_SECURE=true`, run backend on HTTPS |
| Browser console: `CORS error` | FE origin not allowlisted | Add it to `CORS_ALLOWED_ORIGINS` (exact origin, no trailing slash) |
| Job stays `pending` forever | Worker isn't running | `python -m worker.main` |
| Job `failed` with `Orphaned: no live worker` | A worker died mid-run; reaper freed the queue | Resubmit |
| Job `failed` with a `No such file or directory` | `data/` is missing the required asset | Drop the file in; see `README.md` "Required data files" |
| Job `failed` after ~1 hour | Configuration that can't terminate (e.g. fire incidents with no `Engine`) | Validate the station roster has the apparatus the incident set needs |
| `progress.percent` sits at 100% but `status` is still `running` | Progress counts incidents *reported* (early phase); final resolution can take longer | Trust `status`, not the bar |
| Frontend works on `localhost:5173` but not `127.0.0.1:5173` | Same-site rules treat them as different sites for cookies | Pick one and stick to it; or set `VITE_API_BASE` explicitly |

---

## Quick links for client generation

```bash
# Save the spec
curl -s http://localhost:${BACKEND_PORT:-8000}/api/v1/openapi.json > openapi.json

# Generate a TypeScript types file
npx openapi-typescript openapi.json -o src/api-types.ts

# Or import into Postman / Insomnia for an instant "Try it" collection.
```

---

## Got it. Where to start

1. `git clone -b backend-v2 https://github.com/jptalusan/fire_demo3_api.git`
2. Follow `README.md` quickstart, run backend + worker.
3. Open `/docs` — try `POST /auth/register`, `POST /auth/login`, `POST /api/jobs`.
4. Skim `API_REFERENCE.md` while writing your client.
5. When you need to deploy on a separate origin, edit the env vars in §"Auth & cross-origin" above.
