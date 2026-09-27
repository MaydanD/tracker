# Desktop packaging — technical plan (Windows `.exe`)

Status: **plan only**. This document records the investigation and the recommended
approach so packaging can be implemented as its own tested change, separate from
the UX polish pass. No packaging code is introduced by the polish commit.

## 1. What exists today

| Layer | Technology | Notes |
| --- | --- | --- |
| UI | React 19 + TypeScript + Vite | Built to `frontend/dist`, uses `HashRouter` |
| API | FastAPI + SQLAlchemy 2 + Alembic | Application factory `create_app()` in `backend/app/main.py` |
| Data | SQLite (WAL) | `.data/tracker.db`, backups in `.data/backups` |
| Entry | `python -m app` | `backend/app/__main__.py` runs uvicorn |

Two facts already make packaging cheap:

- **`HashRouter`** was chosen so the SPA can load from disk (`file://`) without
  server-side routing. See `frontend/src/App.tsx`.
- **`app/core/paths.py`** already models a frozen build: `is_frozen()` checks
  `sys.frozen`, and `default_data_dir()` returns `%LOCALAPPDATA%\Tracker` for a
  normal install or `data\` next to the executable in portable mode. `TRACKER_PORTABLE`
  is already wired through `Settings`.

## 2. Recommended stack

**pywebview + PyInstaller** — no second frontend or backend.

- **pywebview** opens a native window wrapping the OS web view (WebView2 on
  Windows 11) and points it at the local FastAPI server.
- **PyInstaller** bundles Python, the FastAPI app, the built `frontend/dist` and
  the `owl/` assets into one `.exe`.

Why not the alternatives:

- **Electron / Tauri** would add a second toolchain and a second runtime next to
  Python. Tauri in particular would push the API toward Rust or sidecar processes
  for no product benefit.
- **PyInstaller running uvicorn alone + opening the system browser** keeps the
  "manually open localhost" problem the requirement explicitly wants gone.
- **A pure `--onefile` with a public port** exposes the API beyond loopback; the
  windowed approach can bind to an ephemeral loopback port.

## 3. Architecture of the packaged app

```
Tracker.exe (PyInstaller)
└── launches desktop/__main__.py
    ├── picks a free loopback port (socket bind :0)
    ├── creates the FastAPI app (create_app) with that port's origin in CORS
    ├── starts uvicorn in a background thread (host 127.0.0.1)
    ├── mounts the built SPA and serves it (see §4)
    ├── opens a pywebview window at http://127.0.0.1:<port>/index.html
    └── on window close: signals uvicorn shutdown and joins the thread
```

The window is created with `webview.create_window(..., width=1200, height=800)`
and `webview.start()`. `webview.start()` blocks until the last window closes, so
shutdown naturally follows the event above. The uvicorn server uses
`Server(config).run()` in a daemon thread and is stopped with
`server.should_exit = True`.

## 4. Serving the SPA

Two viable options; the first is recommended.

1. **Mount the built assets on FastAPI** (no second server). Add a small
   `StaticFiles` mount in the app factory when a built `dist` exists:
   - `GET /` → `frontend/dist/index.html`
   - `GET /assets/*` → hashed bundles
   - keep `/api/*` in front of the mount
   The Vite build already emits **relative** asset URLs that work under any origin.
   In development the mount is absent and Vite keeps proxying `/api`, so the same
   backend code serves both modes.
2. Serve `index.html` directly through pywebview's local file loading and let the
   SPA call `http://127.0.0.1:<port>/api`. Then CORS must allow `file://` (opaque
   origin), which is fiddlier. Option 1 avoids it.

Because the window loads from the loopback server, the normal dev CORS origins do
not apply; add `http://127.0.0.1:<port>` (and `http://localhost:<port>`) to
`cors_origins` for the chosen port at startup.

## 5. Integration points (files to touch later)

| Concern | File | Change |
| --- | --- | --- |
| Desktop entry point | `desktop/__main__.py` (new) | port pick, thread, window, shutdown |
| SPA mount | `backend/app/main.py` | mount `frontend/dist` when present |
| CORS for runtime port | `backend/app/core/config.py` | allow the chosen loopback origin |
| Data dir / portable mode | `backend/app/core/paths.py` | already supports frozen builds; verify only |
| Build spec | `tracker.spec` (new PyInstaller spec) | include `frontend/dist`, `owl/`, alembic versions |
| Migrations at start | `desktop/__main__.py` | run `alembic upgrade head` before serving |
| npm build hook | `scripts/build-desktop.ps1` (new) | `npm run build` then PyInstaller |

## 6. Data, backups and upgrades

- **Data stays local.** `%LOCALAPPDATA%\Tracker\tracker.db`; portable mode keeps
  `data\` next to the `.exe`. This is already implemented and must not change, so
  upgrading the executable keeps the same database.
- **Backups keep working** with no changes: the startup SQLite safety copy, the
  logical ZIP `/api/backup` download and the Settings restore flow are all pure
  backend features reached over the same local API.
- Never bundle a database into the `.exe`; ship only code and assets.

## 7. Build outline

```powershell
# 1. Build the SPA
cd frontend; npm ci; npm run build

# 2. Bundle the desktop app + backend
cd ..; pyinstaller tracker.spec
# -> dist\Tracker.exe  (windowed, one file or one folder)
```

`tracker.spec` should collect: `frontend/dist`, `owl/`, `backend/alembic/versions`,
and the hidden imports FastAPI/uvicorn/pydantic need.

## 8. Verification checklist for the packaging change

- Fresh machine: double-click `Tracker.exe` → a window opens, no terminal.
- First run creates `%LOCALAPPDATA%\Tracker\tracker.db` and runs migrations.
- Closing the window stops uvicorn (no lingering process, port is released).
- A second launch reuses the same data directory.
- `Settings → Скачать резервную копию` downloads a valid ZIP; restore round-trips.
- Portable build (`TRACKER_PORTABLE=1`) writes `data\` next to the `.exe`.
- No `5173`, no public port, no "open localhost" instruction is user-visible.

## 9. Open decisions

- **One-file vs one-folder**: one-file is simpler to ship but slower to start
  (it unpacks to a temp dir); one-folder starts faster and is friendlier to
  antivirus. Recommend one-folder for v1.
- **Installer**: NSIS/Inno Setup for a Start-menu shortcut and uninstaller,
  deferred until the portable `.exe` is proven.
- **Code signing**: without a certificate Windows SmartScreen warns on first run;
  this is a distribution concern, not a packaging blocker.
