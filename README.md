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

**Current stage: Stage 12 — Backup / Export / Restore.** Settings (`/#/settings`)
now downloads a complete versioned logical backup and separate JSON/CSV exports.
Restore validates and previews the file, requires explicit confirmation, retains
a safety copy and atomically replaces all user data. Configuration history,
insight snapshots, experiments, IDs and timestamps survive the round trip.
See the [backup format, limits and recovery guide](docs/backup.md).

Stage 11 derives
personal records and milestone achievements from the history it already holds: the
longest habit streak, the best day and completed week, the most habits done in a
day and the most consistent month per habit, plus a short static catalogue of real
achievements with honest historical dates and progress toward locked goals.
Nothing is stored — there is no records table, no mutable counter and no new
migration — so a record is a projection of the data, never a second source of
truth. The Records page is at `/#/records`, the dashboard shows a compact preview,
and the Owl celebrates a new streak record by reusing its existing artwork. See
the [records contract](docs/records.md); the [experiments contract](docs/experiments.md)
and the [Owl contract](docs/owl-assistant.md) still hold.

---

## What works today

- Full logical ZIP backup v1; readable JSON and seven-table CSV ZIP exports;
  validation/preview and confirmed transactional full replacement in Settings.
- FastAPI backend with an application factory, typed settings, logging and one
  consistent error format.
- `GET /api/health` (liveness) and `GET /api/ready` (real database check).
- SQLite through SQLAlchemy 2.x with Alembic migrations.
- **Areas**: create, rename, recolour, archive and restore.
- **Habits**: create and edit the full configuration — area, weight, tracking
  mode, quantity unit, schedule — plus archive/restore and a queryable
  configuration history.
- **Daily tracking** («Итоги дня»): pick any date, past or future, and record each
  habit as `done`, `missed` or a deliberate `skipped` with a separate reason, an
  optional exact quantity and an optional note. Records stay editable, and can be
  cleared back to «no entry».
- **Automatic SQLite backup**: one consistent, timestamped copy per calendar day,
  written with SQLite's own backup API so WAL mode cannot make it incomplete.
- **Schedule, score and streaks**: calendar Mon–Sun quotas, same-week transfers,
  weighted daily/weekly score and current day/week streaks on «Итоги дня».
- **Daily State**: optional mood, energy, wellbeing, sleep, alcohol, gaming,
  computer time and a separate day note, with explicit unspecified/no/yes choices.
- **Dashboard & Calendar**: main dashboard with today's & weekly scores and weight,
  active daily/weekly streaks, weekly quota progress, yesterday's daily state,
  a Monday-first monthly calendar with cell scores and mood indicators,
  interactive day cards with direct navigation to «Итоги дня», and an annual heatmap
  using Stage 4 daily scores.
- **Insights / Analytics**: aggregated discovery, an explicit pair explorer, evidence
  and caveats, SVG charts and daily history snapshots. `GET /api/analytics/insights`,
  detail/history/catalogue endpoints and explicit `POST /api/analytics/insights/refresh`.
- **Owl assistant**: one contextual `owl` state embedded in the dashboard and insight
  responses, rendered as a reusable `OwlAssistantBanner` on both pages. Uses the six
  existing PNGs, keeps a stable fingerprint for session dismiss, and downgrades
  sarcasm for 24 hours client-side — no new table and no duplicated analytics.
- **Experiments**: define a bounded personal experiment (title, hypothesis,
  protocol, start/end dates), track its lifecycle (scheduled/active/completed/
  cancelled) and see a descriptive before/during/after comparison of overall
  progress, individual habits and Daily State, with per-window coverage and an
  overlap warning. `GET/POST /api/experiments`, `GET/PATCH /api/experiments/{id}`
  and `POST /api/experiments/{id}/cancel`. Comparisons reuse the canonical
  dataset: no second statistics engine, no causal claims, missing days never
  become zeros.
- **Records & Achievements**: derived personal bests — longest streak, best day,
  best completed week with coverage, most habits done in a day, and best elapsed
  month per habit — and a static 17-entry achievement catalogue with stable keys,
  real first-reached dates, and progress toward locked goals. `GET /api/records`,
  a compact `records` block on the dashboard, and a Russian `/#/records` page. No
  counters and no migration: everything is computed from the existing history,
  missing days are never failures, and archived habits keep their records.
- **Descriptive analytics API**: `GET /api/analytics/descriptive` with explicit
  inclusive dates and selected variables; typed summaries, coverage, rolling
  values and safe comparisons.
- **Relationships API**: `GET /api/analytics/relationships` for an explicit pair
  or up to 24 selected variables; Pearson, Spearman, point-biserial and Phi with
  pairwise deletion, coverage and typed undefined/unsupported results. Evidence is exposed through the Insights UI.
- **Lag analysis API**: `GET /api/analytics/lags` for one X/Y pair and up to 15
  offsets (-7 to +7 days or weeks), with automatic source-range extension,
  per-lag coverage and the same Stage 7C methods. One dataset build per scan;
  descriptive associations only, with explicit autocorrelation limitations.
- **Confidence API**: `GET /api/analytics/confidence` for one X/Y hypothesis
  (same-period or a single lag, -7..+7). Early/middle/recent segments, explicit
  evidence metrics, a centralized versioned policy and deterministic caveat
  codes with Russian labels. One dataset build for the full period and all
  segments; strength and confidence stay independent. The response also carries
  the compact guardrail verdict for the same hypothesis.
- **Guardrails API**: `GET /api/analytics/guardrails` for one hypothesis, one
  lag family (-7..+7) or a relationship matrix over up to 24 variables. Minimum
  sample, coverage, group balance, effect threshold, within-weekday control,
  temporal blocking and Benjamini–Hochberg FDR across the whole analysis family,
  with per-check statuses, typed blocking reasons and Russian labels. One dataset
  build per request; blocked hypotheses stay in the response.
- React + TypeScript + Vite shell with working Главная, Итоги дня, Календарь, Habits and Areas
  screens, sidebar navigation for all planned screens, and an always-visible
  backend/health indicator.
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
│   │   │   ├── dependencies.py  FastAPI dependency providers (session, clock)
│   │   │   ├── router.py        Aggregate API router
│   │   │   └── routes/          One module per endpoint group
│   │   ├── core/                config, paths, logging, errors, time/clock
│   │   ├── db/                  engine/session lifecycle, backup, ORM models
│   │   ├── domain/              Pure product rules (no DB, no HTTP)
│   │   ├── schemas/             Pydantic request/response models
│   │   └── services/            Use cases that read/write through a session
│   ├── tests/                   pytest suite
│   ├── requirements.txt         Runtime dependencies
│   └── requirements-dev.txt     Runtime + test dependencies
├── frontend/                    React UI
│   ├── src/
│   │   ├── api/                 Typed API client (the only place using fetch)
│   │   ├── components/          Reusable UI pieces (areas/, habits/, daily/)
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

Automatic backups go to `<data directory>\backups`, as
tracker-<date>-<time>.db`. They are separate from the live database on purpose,
and there is one per calendar day at most.

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
| `fc1efb50fa8d` | `daily_habit_entries` (Stage 3) |
| `d5a1c09e2401` | Independent `daily_states` (Stage 5; Stage 4 and 6 had no migrations) |

Upgrading an existing database is just `alembic upgrade head`; each stage adds its
own tables and touches no existing data. Stages 6, 9 and 11 are read-only
presentation/derivation layers (dashboard/calendar, Owl, records & achievements),
so they introduced no new DB migration or schema change.

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
  date-based configuration lookup;
- daily entries: «no entry» as a distinct state, recording today and past days,
  the future-date rules, skip reasons, notes, quantities (including exact
  read-write-read round trips), idempotent re-saves — including two save requests
  that interleave, which must still leave one row — deletion, historical
  configuration lookup, day-view scope and archived-habit history;
- automatic backups: the file is produced, is a valid SQLite database, contains
  data that only the WAL file holds yet, is written once per day, is taken before
  a pending migration, is skipped for in-memory and test databases, never
  overwrites an existing file, leaves nothing behind when the copy fails, and
  logs failures rather than swallowing them.

The frontend suite covers the API client (including write and delete requests and
error envelopes) and the real user paths on the Итоги дня, Habits and Areas
screens: create, edit, filter, archive/restore, validation messages, history and
backend-failure states. The daily screen is checked for Russian wording, the
«нет отметки» / «пропущено» distinction, quantity and unit display, skip reasons,
notes, past-day editing, the future planned-skip rules and clearing a record.

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

### Daily tracking (Stage 3)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/days/{YYYY-MM-DD}` | The whole day: every habit that existed then, its configuration *on that date*, and its record (or `null`) |
| `GET /api/habits/{habit_id}/entries/{YYYY-MM-DD}` | One record (404 when the day holds nothing) |
| `PUT /api/habits/{habit_id}/entries/{YYYY-MM-DD}` | Create or replace that record (idempotent) |
| `DELETE /api/habits/{habit_id}/entries/{YYYY-MM-DD}` | Clear that record, returning the day to «no entry» |

### Dashboard & Calendar (Stage 6)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/dashboard` | Main dashboard summary: today score/weight/habits, current week score/quota progress, active streaks, yesterday's Daily State, Owl and a compact records preview |
| `GET /api/calendar?start=YYYY-MM-DD&end=YYYY-MM-DD` | Aggregated date range summary for monthly calendar and yearly heatmap (daily score, obligations, mood indicator) |
| `GET /api/days/{YYYY-MM-DD}/overview` | Aggregated overview for a day card: daily score, habit entry details, and Daily State summary |

### Records (Stage 11)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/records` | Derived personal records (`summary`, `records`, `achievements`, `recent_achievements`). Read-only and un-cached: deleted history can change a record. |

There are deliberately no delete endpoints for habits or areas: they are archived,
so historical records keep resolving. The only delete in the API removes a daily
*entry* — the user's own note about a day.

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
- **weight** — `1` normal, `2` important, `3` key (used by the score engine);
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
slots — Stage 4 satisfies a weekly quota with a completion on another day of
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

### Daily tracking (Stage 3)

«Итоги дня» records what happened for each habit on one calendar date. Open any
past or future date, state the outcome per habit, and change it later.

**«Нет отметки» and «Пропущено» are different states.** A missing record means the
user has said nothing about that habit on that day. `missed` exists only when the
user states it. Tracker never derives a miss from silence — not for yesterday and
not for last year — and clearing a record returns the day to «нет отметки» rather
than to `missed`. Automatic evaluation belongs to Stage 4 and must not be written
back into the records.

| Status | Meaning | Allowed on |
| --- | --- | --- |
| `done` | Performed | today, past |
| `missed` | The user states it was not performed | today, past |
| `skipped` | A deliberate/planned skip | past, today, **future** |

A future date accepts a planned skip and nothing else, and the backend enforces
that on its own: the screen simply does not offer `done`/`missed` for a day that
has not happened, because offering an action that would be refused is worse than
not offering it. «Сегодня», «Вчера» and «Завтра» come from the server's date, so
the screen and the API always agree on which rules apply.

**One habit and one date hold at most one record.** Saving is a `PUT`: the record
is replaced, never duplicated, so saving the same day twice (or re-saving after a
mistake) leaves exactly one row. `habit_id + entry_date` is unique in the database.

**Skip reason and note are separate fields.** A `skipped` record requires a reason
(travel, illness, holiday, a deliberate rest day, or free text); `done`/`missed`
may not carry one, so a reason can never drift into a different meaning. The note
is optional for any status.

**Quantity is optional and structured.** It only exists for `binary_quantity`
habits, and it is validated against the configuration that was effective **on the
recorded date** — the unit and decimal rule of that day, not of today:

- a `binary` habit rejects a quantity outright;
- the unit comes from the historical version and is shown with the value;
- if the historical version forbids decimals, a fraction is rejected;
- if it allows them, up to six decimal places are accepted, and a value with
  more precision is rejected rather than silently rounded.

Quantities are stored as an exact integer number of millionths
(`quantity_value_micro`), not as `REAL`/`NUMERIC` (SQLite's numeric affinity is
binary floating point, which turns 6.4 into 6.4000000000000004) and not as text.
The API renders the field as a JSON number, because JSON has no decimal type.

Six places is a deliberate bound rather than an implementation detail: it is far
beyond what any hand-recorded unit needs (a gram of a body weight in kg, a metre
of a distance in km), the value is non-negative and capped at 1 000 000, and the
scaled integer therefore stays well inside a signed 64-bit column.

### Schedule + Streak + Score (Stage 4)

The week is always **Monday–Sunday**, never rolling seven days. `daily` creates
one obligation per active date. `weekdays` means a flexible weekly quota equal to
the number of preferred days; `times_per_week` means N completions. Tue/Thu/Sat
can satisfy Mon/Wed/Fri, but completions cannot move between weeks. Each `done`
counts once, regardless of quantity. Preferred days never disable recording.

The only score formula is **completed required weight / required weight × 100**.
Weights 1/2/3 mean normal/important/key. Daily score includes only daily habits;
weekly score sums their dated obligations plus each weekly quota times its
weight. Weekly credit is capped at quota, although progress shows the real count
(e.g. 5/3). `missed`, `skipped` (any reason) and no entry contribute zero without
removing required weight. Zero obligations return `null`, shown as
«Нет обязательных привычек». Reads never write implicit `missed` entries or
materialize scores/streaks; no schema migration is needed.

Daily streaks count consecutive `done` days. Historical missed/skipped/unrecorded
required days break them; an unfinished today preserves yesterday's streak and a
`done` today extends it immediately. Weekly streaks count consecutive successful
Mon–Sun quotas. An incomplete current week preserves previous weeks; reaching
quota extends the streak immediately. An unfinished Sunday is still pending;
failure is resolved on Monday. Live score already includes outstanding
obligations, including the rest of this week's daily dates. All current-period
decisions use the injected Clock.

**Historical configuration, including mixed weeks:** daily dates each use their
own effective version. A weekly component takes quota, weight and preferred days
from the **first active weekly-scheduled date of that calendar week**. Later
weekly edits apply to the following week. Only dates whose effective schedule is
weekly contribute to that quota; dates with daily schedules contribute separately.
This handles daily ↔ weekly changes without double credit. A mixed week's API
exposes both counts, and the UI explains them. Weekly streaks evaluate the weekly
component; daily streaks stop at a schedule-unit change. Creation midweek starts
daily obligations on creation, but starts a **full weekly quota, without
proration**, even if too few days remain. Existing same-day version collapse
remains authoritative; no new snapshot/history mechanism is introduced.

**Archive boundary:** existing UTC `archived_at` is converted to a local date;
that date is the exclusive cutoff for obligations. Earlier progress stays
queryable; the already-started weekly quota remains full, and later weeks add
nothing. Archived streaks are evaluated at the last active date (a weekly quota
still resolves at Sunday end). Entries on/after the cutoff remain readable and
editable through Stage 3, but are outside score obligations. The existing restore
operation clears `archived_at`, so previous archive intervals cannot be recovered;
restoring again treats the lifetime as active. We do not invent an archive date
from `updated_at` or add an archive-event subsystem. A legacy archived row missing
its timestamp creates no derived obligations; its records remain readable.
Changing the system timezone can change the local date of a UTC archive boundary.

| Read-only endpoint | Result |
| --- | --- |
| `GET /api/progress/days/{YYYY-MM-DD}` | Daily score, weights, obligations and raw entry states; selected calendar week; current streaks |
| `GET /api/progress/weeks/{YYYY-MM-DD}` | Normalized Mon–Sun bounds, score, weights, per-habit quota/count/preferred days and satisfied/pending/failed status |
| `GET /api/habits/{habit_id}/progress` | Current streak, days/weeks unit, as-of date, current weekly progress |

«Итоги дня» adds compact daily/weekly scores, weighted totals, per-habit progress,
current streaks and preferred-day explanations. Changing or clearing an entry
refreshes them; late responses cannot show another date's score. The selected
date controls day/week progress; streaks explicitly show their current as-of date.
Stage 4 added no new dashboard, calendar, heatmap or state tracking. Full boundary
semantics are specified in [PROJECT-SPEC.md §10.4](PROJECT-SPEC.md#104-реализовано-stage-4--schedule--streak--score).

Stage 4 regression tests cover domain rules, database/API history and read
purity, calendar/creation/configuration/archive boundaries, quantity-independent
completion, score caps, current-period grace, Russian UI, off-preferred-day
recording, clearing, retries and late responses. Contract fixtures in frontend
tests do not reimplement the scoring engine.

### Daily State (Stage 5)

Daily State observes a **calendar date**, separately from habits. One unique
`state_date` has at most one row in `daily_states`, with no habit foreign key.
All observation fields are nullable; no defaults manufacture answers:

- `mood`, `energy`, `wellbeing`: integer **1–5**, or `null` (unspecified).
- `sleep_status`: `underslept`, `normal`, `overslept`, or `null`.
  `sleep_minutes`: optional integer **0–1440**, independent of the category.
- `alcohol`, `gaming`, `computer_overuse`: **null / false / true** mean
  unspecified / explicitly no / explicitly yes. An unfilled day is never
  interpreted as sober or without gaming/computer use.
- `alcohol_detail`: trimmed optional text, at most 200 characters, allowed only
  with `alcohol=true`. A nonblank detail with false/null is rejected (422).
- `gaming_minutes`: optional integer **0–1440**. Null gaming requires null
  minutes; false gaming permits null or zero, and rejects positive minutes.
- `computer_minutes`: optional integer **0–1440**, independent of the subjective
  overuse flag. 180 minutes with false/null is valid; no threshold derives a flag.
- `note`: separate day note, trimmed, at most 500 characters. It never replaces
  habit notes, skip reasons or alcohol details. Blank text normalizes to null.

Partial records (even just `false`, zero minutes or a note) are valid. Completely
empty records are rejected after normalization; clearing the day uses DELETE.
Numeric and boolean inputs are strict: strings, fractional minutes and numbers
in place of booleans are rejected. Database CHECKs backstop ranges, enum values,
cross-field consistency and nonempty records.

| Endpoint | Result |
| --- | --- |
| `GET /api/days/{YYYY-MM-DD}/state` | `{state_date, today, state}`; absent state is `null`, including a future date |
| `PUT /api/days/{YYYY-MM-DD}/state` | Full replacement/upsert, returns the record; omitted fields become null |
| `DELETE /api/days/{YYYY-MM-DD}/state` | Idempotent removal, 204; subsequent GET returns `state: null` |

Today and all past dates are editable, including dates before the first habit.
Future PUT/DELETE are rejected with `422 future_daily_state`, using the existing
injected Clock. GET remains allowed. UTC creation/update timestamps are metadata,
not the observation date. SQLite `ON CONFLICT DO UPDATE` makes concurrent first
saves atomic and preserves the row id and creation timestamp.

«Итоги дня» has a compact Russian «Состояние дня» block, segmented scales and
tri-state choices, hours/minutes inputs, conditional alcohol/gaming details,
save and clear actions. Unspecified is visually distinct from no. The server's
today controls future disabling. Date-keyed resource/form lifetimes protect
drafts against delayed GET/PUT/DELETE responses. Saving only updates this block.

Daily State **does not change obligations, scores, weights, schedules, streaks
or habit entries**. Regression tests compare full day/week/streak responses and
manual entries before and after saving, editing and deleting state. Future habit
planned skips remain allowed. Domain/API/DB tests also cover every field boundary,
tri-state persistence, concurrent saves, migration preservation and UI races.

Stage 5 ends at collection: no correlations, averages, charts, predictions,
recommendations, experiments, achievements, reminders, notifications, auth or sync.

### Backups

Starting the application writes a safety copy of the database, at most once per
calendar day, into `<data dir>/backups` as `tracker-<date>-<time>.db`.

The copy is made with SQLite's own online backup API rather than `shutil.copy`.
The database runs in WAL mode, which keeps recent committed data in
`tracker.db-wal` until a checkpoint: copying only `tracker.db` can therefore miss
the newest records or capture a torn page. Going through a SQLite connection
takes a consistent snapshot instead, including committed WAL content, while the
application holds the file open.

This raw SQLite mechanism is deliberately minimal: no scheduler or cloud; the
Stage 12 UI restores logical ZIP backups, not these `.db` files. A small
retention window keeps the most recent automatic backups and never touches files
it did not create. In-memory databases, the `test` environment and a database that
does not exist yet are skipped, so a test run cannot litter real files.

An existing file is never written over: the name is claimed exclusively, so two
starts in the same second cannot interleave into one file. A copy that fails
removes the file it had started, because a truncated file with a valid-looking
name would both look like a real backup and stop the next start from retrying.
Either way the failure is logged with its traceback and never stops startup.

### Editing, archiving and the UI

`Итоги дня`, `Привычки` and `Сферы` are working screens. Habits can be filtered by
area and include archived items on request; archiving hides an item from the
default list while keeping its history; the «История» action on a habit shows every
configuration version with the date it became effective. Form validation prevents
contradictory configurations client-side, and the server remains the authority —
its `422`/`409` codes are translated into Russian messages and shown on the form
without discarding typed input.

**Archiving never hides recorded days.** A habit with a record on the chosen date
still appears on «Итоги дня» (marked «В архиве») and that record stays editable and
clearable. A habit that was archived before anything was recorded simply does not
appear. No entry is ever deleted or rewritten because a habit was archived.

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
  shape, weights, quantity units, the version-planning rule, the daily-entry rules)
  with no session and no FastAPI; `app/services` runs use cases against a session;
  `app/api` is HTTP wiring only. The rules that are expensive to get wrong are
  unit tested without a database.
- **One clock for every calendar rule.** "Today" comes from an injectable
  `Clock` (`app.state.clock`), never from a scattered `date.today()`, so the
  future-date rules are testable and the API and the screen cannot disagree about
  which rules apply.
- **Structural rules exist twice on purpose:** in the domain *and* as SQLite
  `CHECK` constraints, so no code path can persist an invalid configuration
  (weight outside 1–3, a quantity unit on a binary habit, a schedule whose shape
  contradicts its type).
- **Minimal dependencies.** No state management library, no ORM for the frontend,
  no form library, no observability stack, no Docker, no PostgreSQL, no
  authentication.

---

## Known limitations

- **No archive-event history.** The existing model retains only the current
  `archived_at`; restore clears it. Stage 4 uses this boundary as documented above.
- **Full partial-week quota.** Creation or schedule change midweek does not
  prorate a weekly quota; the UI shows the required count explicitly.
- Still absent: recommendation/prediction engines, native `.xlsx` export and the
  Windows executable. Insights discovery is bounded;
  the UI explorer currently selects daily variables. History keeps the latest
  evaluation per hypothesis per day and returns the latest 200 snapshots.
- **The Owl is guidance only.** It selects one deterministic state from existing
  data, keeps no history, and its sarcasm is a presentation choice behind a
  client-side cooldown — never a user-facing judgement of the person.
- **Backups stay local.** Logical restore supports full replacement only, with
  64 MiB upload / 256 MiB expanded limits (configurable). Safety copies are retained
  in `<data dir>/backups` until manually removed. Existing daily startup SQLite
  copies retain their own small retention window. No cloud, encryption, monthly
  snapshots or scheduled logical backups. Details: [backup.md](docs/backup.md).
- Habits cannot be reordered manually, and there is no bulk edit.
- A daily entry cannot be backdated: the habit must already have existed on the
  date you record. Configuration changes likewise cannot be backdated.
- Configuration changes cannot be backdated (an edit always takes effect today or
  later); the service layer already accepts an explicit effective date for when
  that becomes useful.
- **Guardrails cannot turn association into causation.** Statistical guardrails
  reduce the risk of reading chance or calendar artifacts as evidence, but `pass`
  is not proof, `p`/`q` are not probabilities that an association is true, and the
  effect thresholds are product policy rather than a statement about the real
  world. Weekday control only removes a linear weekday baseline, and low or
  uneven coverage is reported rather than corrected (Stage 7D).
- No authentication: the API binds to `127.0.0.1` and is meant for one local user.
- No log files and no packaging step; run it from source with the commands above.

## Next stage

Stage 12 Backup / Export / Restore is implemented; the official format is logical
ZIP v1, with validation, explicit confirmation and atomic full replacement.
Desktop packaging is deferred beyond Stage 12. Stage 13 focuses on hardening;
packaging requires its own tested scope. Stage 11 remains a derived long-term-progress layer:
personal records and milestone achievements are computed from the current history,
never stored. Stage 4 remains the source of progress and streaks, Stage 7A the
canonical dataset, and Stage 8 the source of every statistical value. Later product
stages remain separate: there is no causal inference, no significance engine for
experiments, no recommendations, prediction or LLM generation. See
[Stage 12 format and recovery](docs/backup.md),
[Stage 11 architecture](docs/records.md),
[Stage 10 architecture](docs/experiments.md),
[Stage 9 architecture](docs/owl-assistant.md) and
[Stage 8 architecture and limitations](docs/analytics-insights.md).
