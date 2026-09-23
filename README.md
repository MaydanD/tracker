# Tracker

Tracker is a **local, single-user desktop application** for habit tracking, daily
state tracking and long-term personal analytics. Its purpose is not gamification:
it accumulates a clean personal dataset over months and years so that Tracker can
later surface evidence-backed observations such as *"days with alcohol are
associated with lower energy the next day"* (association, never causation).

There is no account system, no cloud dependency and no server deployment. All
data stays in a local SQLite file.

The product specification lives in [`PROJECT-SPEC.md`](PROJECT-SPEC.md) and is the
source of truth for what Tracker will become.

**Current stage: Stage 1 — Foundation.** The technical foundation is complete;
almost no product features exist yet. See
[Known Stage 1 limitations](#known-stage-1-limitations).

---

## What works today

- FastAPI backend with an application factory, typed settings, logging and one
  consistent error format.
- `GET /api/health` (liveness) and `GET /api/ready` (real database check).
- SQLite through SQLAlchemy 2.x with Alembic migrations and an initial migration.
- React + TypeScript + Vite shell with sidebar navigation for all planned
  screens, and an always-visible backend/health indicator.
- Backend tests (pytest) and frontend tests (Vitest) that never touch your real
  database, plus a TypeScript-checked production build.

---

## Repository structure

```
tracker/
├── PROJECT-SPEC.md              Product specification (source of truth)
├── README.md
├── backend/                     Python API
│   ├── alembic.ini              Alembic configuration
│   ├── alembic/
│   │   ├── env.py               Resolves the DB from app settings
│   │   └── versions/            Migration scripts
│   ├── app/
│   │   ├── main.py              Application factory (create_app)
│   │   ├── __main__.py          `python -m app` dev server entry point
│   │   ├── api/
│   │   │   ├── dependencies.py  FastAPI dependency providers
│   │   │   ├── router.py        Aggregate API router
│   │   │   └── routes/          One module per endpoint group
│   │   ├── core/                config, paths, logging, errors, time
│   │   ├── db/                  engine/session lifecycle, base, ORM models
│   │   ├── schemas/             Pydantic request/response models
│   │   └── services/            Business logic independent of HTTP
│   ├── tests/                   pytest suite
│   ├── requirements.txt         Runtime dependencies
│   └── requirements-dev.txt     Runtime + test dependencies
├── frontend/                    React UI
│   ├── src/
│   │   ├── api/                 Typed API client (the only place using fetch)
│   │   ├── components/          Reusable UI pieces
│   │   ├── hooks/               React hooks (backend status polling)
│   │   ├── layout/              Application shell: sidebar + top bar
│   │   ├── pages/               One file per planned screen
│   │   └── styles/              CSS tokens and layout
│   ├── vite.config.ts           Dev proxy + Vitest configuration
│   └── package.json
├── scripts/                     PowerShell helpers (setup / run / check)
└── .data/                       Local runtime data — created on first run, git-ignored
```

---

## Prerequisites

- **Windows 11** (developed and verified there; the code is not Windows-only)
- **Python 3.11+** — verified with 3.13. Check with `python --version`.
- **Node.js 20+** with npm — verified with Node 24 / npm 12. Check with
  `node --version`.
- **PowerShell** (bundled with Windows) for the helper scripts.

No Docker, PostgreSQL, WSL, Make, bash or cloud services are required.

---

## Quick start

Open two terminals in the repository root.

**Terminal 1 — backend**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app --reload
```

The API is then on <http://127.0.0.1:8000> (interactive docs at `/docs`).

**Terminal 2 — frontend**

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` to the backend,
so the browser only ever talks to one origin and the header status should read
**Connected** with `Database: ok`.

If another project already uses port 5173, Vite automatically picks the next free
port — watch the terminal output for the URL. If you move the backend to a
different port, start Vite with
`$env:VITE_API_PROXY_TARGET='http://127.0.0.1:8001'; npm run dev`.

### Helper scripts (optional)

From the repository root:

```powershell
powershell -File scripts\setup-backend.ps1    # venv, dependencies, migrations
powershell -File scripts\dev-backend.ps1      # migrate + start the API with reload
powershell -File scripts\dev-frontend.ps1     # install if needed + start Vite
powershell -File scripts\check.ps1            # every Stage 1 quality gate
```

---

## Where local runtime data is stored

| Situation | Data directory |
| --- | --- |
| Development (default) | `<repository>\.data` |
| Override | `TRACKER_DATA_DIR` |
| Packaged build (planned) | `%LOCALAPPDATA%\Tracker` |
| Portable packaged build (planned) | `data\` next to the executable |

The SQLite database is `<data directory>\tracker.db`. It is created by
`alembic upgrade head` (`python -m app` also creates the directory on startup).
`.data/` is git-ignored, and no database is ever committed.

Logs go to stdout only; there is no log file yet.

---

## Configuration

Settings are typed and read from the environment with the `TRACKER_` prefix,
optionally from a `.env` file (copy `backend/.env.example` to `backend/.env`).
See [`backend/.env.example`](backend/.env.example) for the full list.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRACKER_APP_ENV` | `development` | `development`, `test` or `production` |
| `TRACKER_HOST` | `127.0.0.1` | Bind address |
| `TRACKER_PORT` | `8000` | Bind port |
| `TRACKER_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `TRACKER_DATA_DIR` | `<repo>\.data` | Directory holding `tracker.db` |
| `TRACKER_DATABASE_URL` | derived | Full SQLAlchemy URL; overrides `TRACKER_DATA_DIR` |
| `TRACKER_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins allowed to call the API |
| `TRACKER_PORTABLE` | `false` | Packaged build: keep data next to the executable |

Unrecognised `TRACKER_*` variables are reported as a warning at startup so typos
(`TRACKER_LOG_LEVL`) are visible instead of silently ignored.

Frontend variables use the `VITE_` prefix; see `frontend/.env.example`.

---

## Database migrations

Alembic resolves the database exactly like the application does, so migrations
always land in the same file the API uses (`backend/alembic/env.py`).

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head      # apply all migrations
.\.venv\Scripts\python.exe -m alembic current           # current revision
.\.venv\Scripts\python.exe -m alembic history           # revision history
.\.venv\Scripts\python.exe -m alembic downgrade -1      # step back one revision
.\.venv\Scripts\python.exe -m alembic upgrade head --sql  # print SQL, touch nothing

# after changing a model:
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "add habits"
.\.venv\Scripts\python.exe -m alembic check             # fail if models drifted
```

Migration scripts live in `backend/alembic/versions/`. Keep `alembic check`
passing: it fails when models and migrations disagree.

To migrate a throwaway database instead of your real one:

```powershell
$env:TRACKER_DATA_DIR="$env:TEMP\tracker-scratch"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

---

## Running the tests

```powershell
# Backend (pytest) — every test uses its own temporary data directory
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest -k ready -v      # single area, verbose

# Frontend (Vitest)
cd frontend
npm test            # single run
npm run test:watch  # watch mode
npm run typecheck   # TypeScript only
npm run build       # typecheck + production build into frontend/dist
```

Or run everything at once: `powershell -File scripts\check.ps1`.

The backend suite covers the health and readiness endpoints (including the
database-failure path), configuration behaviour, session lifecycle and SQLite
pragmas, the application factory and error envelopes, and the migrations
(fresh database, no model drift, downgrade/upgrade round trip).

---

## API

| Endpoint | Purpose | Success | Failure |
| --- | --- | --- | --- |
| `GET /api/health` | Process is alive | `200 {"status":"ok","app":"Tracker","version":"0.1.0","environment":"development"}` | — |
| `GET /api/ready` | Database reachable (real query) | `200 {"status":"ready","checks":{"database":"ok"}}` | `503 {"status":"unavailable","checks":{"database":"error"}}` |

Readiness reports *state* rather than raising, so the frontend can show "database
unavailable" without parsing an error body. Every other failing response uses one
envelope:

```json
{ "error": { "code": "not_found", "message": "Not Found" } }
```

OpenAPI is served at `/api/openapi.json`, Swagger UI at `/docs`.

---

## Architecture notes

- **One application factory.** `create_app()` assembles settings, database,
  middleware, error handlers and routers. Nothing touches the filesystem at
  import time, which keeps tests and the future desktop shell predictable.
- **No global session.** The engine and session factory live on `app.state`; each
  request gets a short-lived session that is rolled back on error and only
  committed explicitly.
- **SQLite is tuned deliberately:** `NullPool` + `check_same_thread=False` for
  FastAPI's thread pool, and `foreign_keys=ON`, `journal_mode=WAL`,
  `synchronous=NORMAL`, `busy_timeout=5000` on every connection.
- **Timestamp policy:** all stored timestamps are UTC. SQLite drops the offset, so
  date logic (schedules, streaks, day boundaries) must build on explicit calendar
  dates rather than local timestamps.
- **Migrations from the start,** with a naming convention for constraints and
  Alembic batch mode enabled, because SQLite cannot alter most columns in place.
- **Storage decisions kept open for later stages:** one local user, indefinite
  retention, SQLite as the authoritative store, and a data directory that is
  separate from the source tree so backups, Excel export and portable packaging
  can be added without reorganising anything.
- **`HashRouter`** in the frontend so the future pywebview/PyInstaller build can
  load the SPA from disk without rewriting navigation.
- **Minimal dependencies.** No state management library, no ORM for the frontend,
  no observability stack, no Docker, no PostgreSQL, no authentication.

---

## Known Stage 1 limitations

- **No product features yet.** Habits, areas, daily entries, quantities, streaks,
  schedules, mood/energy/sleep, factors, heatmaps, analytics, insights, the owl,
  experiments, records, backup/export and the Windows executable all belong to
  later stages. The only database table is the internal `app_metadata` key/value
  table used to prove migrations work.
- Navigation entries are placeholders; each states the stage that fills it in.
- No authentication: the API binds to `127.0.0.1` and is meant for one local user.
- No backup, export or restore yet, so the database file is the only copy of your
  data. Do not treat Stage 1 data as precious.
- No log files and no packaging step; run it from source with the commands above.
- Frontend tests cover the API client and the shell, not real screens.

## Next stage

**Stage 2 — Areas and Habits:** areas CRUD, habits CRUD with weight, archive
state, tracking mode, structured quantity configuration, schedule configuration
and a basic configuration-history strategy (see `PROJECT-SPEC.md`, section 25).
