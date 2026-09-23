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

**UI language: Russian.** All user-facing text, including errors and schedule labels,
is Russian (PROJECT-SPEC.md §2.1); API fields and codes remain English.

**Current stage: Stage 2 — Areas & Habits.** Areas and habits can be managed;
recording daily completions is Stage 3. See
[Known Stage 2 limitations](#known-stage-2-limitations).

---

## What works today

- FastAPI backend with an application factory, typed settings, logging and one
  consistent error format.
- `GET /api/health` (liveness) and `GET /api/ready` (real database check).
- SQLite through SQLAlchemy 2.x with Alembic migrations.
- **Areas**: create, rename, recolour, archive and restore.
- **Habits**: create and edit the full configuration — area, weight, tracking
  mode, quantity unit, schedule — plus archive/restore and a queryable
  configuration history.
- React + TypeScript + Vite shell with working Habits and Areas screens, sidebar
  navigation for all planned screens, and an always-visible backend/health
  indicator.
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
│   │   ├── domain/              Pure product rules (no DB, no HTTP)
│   │   ├── schemas/             Pydantic request/response models
│   │   └── services/            Use cases that read/write through a session
│   ├── tests/                   pytest suite
│   ├── requirements.txt         Runtime dependencies
│   └── requirements-dev.txt     Runtime + test dependencies
├── frontend/                    React UI
│   ├── src/
│   │   ├── api/                 Typed API client (the only place using fetch)
│   │   ├── components/          Reusable UI pieces (areas/, habits/, shared)
│   │   ├── hooks/               React hooks (backend status, areas, habits)
│   │   ├── layout/              Application shell: sidebar + top bar
│   │   ├── pages/               One file per planned screen
│   │   └── styles/              CSS tokens, layout and product UI
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

Migration scripts live in `backend/alembic/versions/`:

| Revision | Contents |
| --- | --- |
| `0001` | Internal `app_metadata` table (Stage 1) |
| `8c12a1c62d83` | `areas`, `habits`, `habit_versions` (Stage 2) |

Upgrading an existing Stage 1 database is just `alembic upgrade head`; the Stage
2 migration adds its tables without touching existing data.

Keep `alembic check` passing: it fails when models and migrations disagree.

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

The backend suite covers:

- the health and readiness endpoints, including the database-failure path;
- configuration behaviour, session lifecycle and SQLite pragmas;
- the application factory, error envelopes and the documented route set;
- migrations: fresh database, upgrade from Stage 1, `alembic check` drift, and a
downgrade/upgrade round trip;
- the domain rules for schedules, weights, quantity units and version planning —
  tested without a database;
- area and habit endpoints end to end, including archive rules, area filtering,
  and the SQLite `CHECK` constraints that backstop the domain;
- configuration history: same-day and later edits, preserved old versions, and
  date-based configuration lookup.

The frontend suite covers the API client (including write requests and error
envelopes) and the real user paths on the Habits and Areas screens: create,
edit, filter, archive/restore, validation messages, history and backend-failure
states.

---

## API

### System

| Endpoint | Purpose | Success | Failure |
| --- | --- | --- | --- |
| `GET /api/health` | Process is alive | `200 {"status":"ok","app":"Tracker","version":"0.1.0","environment":"development"}` | — |
| `GET /api/ready` | Database reachable (real query) *and* schema at the expected revision | `200 {"status":"ready","checks":{"database":"ok","migrations":"ok"}}` | `503` with `checks.database = "error"` (unreachable) or `checks.migrations = "pending"` (run `alembic upgrade head`) |

### Areas (Stage 2)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/areas?include_archived=false` | Active areas, or every area |
| `POST /api/areas` | Create an area (409 on a duplicate active name) |
| `GET /api/areas/{area_id}` | Fetch one area |
| `PATCH /api/areas/{area_id}` | Rename and/or recolour |
| `POST /api/areas/{area_id}/archive` | Archive (409 while it has active habits) |
| `POST /api/areas/{area_id}/unarchive` | Restore to the active list |

### Habits (Stage 2)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/habits?include_archived=false&area_id=` | List habits (grouped order: area, then name) |
| `POST /api/habits` | Create a habit with its first configuration version |
| `GET /api/habits/{habit_id}` | Fetch a habit with its current configuration |
| `PUT /api/habits/{habit_id}` | Replace the configuration (recorded as a version) |
| `POST /api/habits/{habit_id}/archive` | Archive (history is kept) |
| `POST /api/habits/{habit_id}/unarchive` | Restore to the active list |
| `GET /api/habits/{habit_id}/versions` | Configuration history, newest first |
| `GET /api/habits/{habit_id}/configuration?on=YYYY-MM-DD` | The configuration effective on a date |

There are deliberately no delete endpoints: habits and areas are archived, so
historical records keep resolving.

Readiness reports *state* rather than raising, so the frontend can show "database
unavailable" without parsing an error body. Every other failing response uses one
envelope:

```json
{ "error": { "code": "not_found", "message": "Not Found" } }
```

OpenAPI is served at `/api/openapi.json`, Swagger UI at `/docs`.

---

## Areas and habits (Stage 2)

### Areas

An Area is a broad life sphere (Health, Development, Work, Household) and is
expected to number four to six. Areas have a name and a colour, are unique by
name among *active* areas (case-insensitive), and are archived rather than
deleted. An Area that still has active habits cannot be archived — archive or
move its habits first. Restoring a habit also requires an active Area.

### Habits

A habit belongs to exactly one area and carries:

- **name** and optional description (duplicate habit names within an Area are allowed);
- **weight** — `1` normal, `2` important, `3` key (used by the future score
  engine);
- **tracking mode** — `binary` (done / not done) or `binary_quantity`;
- **quantity configuration** — for `binary_quantity`, a unit (free text:
  `pages`, `minutes`, `km`, `reps`, …) and whether decimals are expected.
  Quantity is structured configuration, never a note, and no unit conversion is
  performed anywhere;
- **schedule** — see below.

### Schedule types

| Type | Meaning | Weekly quota |
| --- | --- | --- |
| `daily` | Expected every day | 7 (derived) |
| `weekdays` | Preferred days, e.g. Mon/Wed/Fri | Number of selected days (derived) |
| `times_per_week` | N completions in the week, no fixed days | N, 1–7 |

The canonical week is **Monday–Sunday**; weekly quotas are calendar-week quotas,
never rolling seven-day windows. Preferred weekdays are *preferences*, not fixed
slots — Stage 4 may satisfy a weekly quota with a completion on another day of
the same week. For weekday schedules the quota is derived from the selected
days, so "Mon/Wed/Fri with a quota of 2" cannot be expressed: there is exactly
one source of truth. A habit completes at most once per calendar date, which is
why a weekly quota cannot exceed 7.

The API returns the derived `weekly_required_count` and a human-readable
`summary` (for example `Mon, Wed, Fri (3 per week)`), so the UI does not
reimplement schedule rules. The Russian UI formats its own schedule label from
structured fields and the server-derived quota, without parsing the English summary.

### Configuration history

Habit configuration lives in effective-dated versions (earlier days are preserved;
same-day edits update the current version)
(`habit_versions`) rather than on the habit row. "Current configuration" is
simply the latest version, so a habit and its own history cannot drift apart,
and "what weight applied on date X?" is answered from the same table that
recorded it:

- creating a habit writes version 1, effective from today;
- saving an edit effective later appends a new version;
- saving an edit on the same day updates that day's version (one version per
  habit per calendar day);
- saving an unchanged configuration creates no version at all;
- an edit that would take effect *before* the current version is rejected with
  `422 invalid_configuration_date` instead of rewriting recorded meaning.

Effective dates are calendar dates in the machine's local timezone (Tracker runs
on the user's own machine), while `created_at`/`updated_at` timestamps stay UTC.

### Editing and archiving in the UI

`Привычки` and `Сферы` are working screens. Habits can be filtered by area and
include archived items on request; archiving hides an item from the default list
while keeping its history; the «История» action on a habit shows every
configuration version with the date it became effective. Form validation
prevents contradictory configurations client-side, and the server remains the
authority — its `422`/`409` codes are translated into Russian messages and shown on the form without discarding
typed input.

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
- **Three backend layers.** `app/domain` holds pure product rules (schedule
  shape, weights, quantity units, the version-planning rule) with no session and
  no FastAPI; `app/services` runs use cases against a session; `app/api` is HTTP
  wiring only. The rules that are expensive to get wrong are unit tested without
  a database.
- **Structural rules exist twice on purpose:** in the domain *and* as SQLite
  `CHECK` constraints, so no code path can persist an invalid configuration
  (weight outside 1–3, a quantity unit on a binary habit, a schedule whose shape
  contradicts its type).
- **Minimal dependencies.** No state management library, no ORM for the frontend,
  no form library, no observability stack, no Docker, no PostgreSQL, no
  authentication.

---

## Known Stage 2 limitations

- **No daily tracking yet.** Recording completions, quantities per day, notes,
  skips with reason, historical day editing and future skips are Stage 3. A habit
  therefore cannot be marked done anywhere in the UI.
- **No schedule execution.** Streaks, day/week scores and flexible same-week
  completion allocation are Stage 4; Stage 2 stores and validates the schedule
  only.
- Still absent: mood/energy/well-being/sleep/factors, dashboard content,
  calendar and heatmaps, analytics, insights, the owl, experiments, records,
  backup/export and the Windows executable.
- **No backup yet.** The Stage 3 plan includes simple automatic SQLite backups;
  until then the database file is the only copy of your data.
- Habits cannot be reordered manually, and there is no bulk edit.
- Configuration changes cannot be backdated (an edit always takes effect today or
  later); the service layer already accepts an explicit effective date for when
  that becomes useful.
- No authentication: the API binds to `127.0.0.1` and is meant for one local user.
- No log files and no packaging step; run it from source with the commands above.

## Next stage

**Stage 3 — Daily Tracking + Early Backup:** daily habit entries with
`done`/`missed`/`skipped-with-reason`, structured per-day quantities, per-habit
notes, historical editing, future planned skips, and a simple automatic
timestamped SQLite backup (see `PROJECT-SPEC.md`, section 27).
