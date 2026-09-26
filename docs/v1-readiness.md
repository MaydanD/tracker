# Tracker v1 Operational Readiness & Operations Guide

## 1. Overview & Architecture Guarantees
Tracker is a single-user, local-first habit and daily-state tracking application.

- **Backend Architecture:** FastAPI ASGI application using SQLAlchemy 2.x and Alembic migrations.
- **Database Engine:** SQLite (WAL mode, `foreign_keys=ON`, `busy_timeout=5000`, `synchronous=NORMAL`).
- **Data Integrity & Consistency:**
  - Foreign key constraints are enforced on every database connection.
  - Core mutating operations (habit versioning, daily entry logging, experiment creation/cancellation, logical restore) execute in atomic transactions (`session.commit()` on success, `session.rollback()` on failure).
  - Multi-table logical restore uses `BEGIN IMMEDIATE` transaction locking and FK-safe order of execution.
- **Read-Only Invariants:**
  - GET endpoints (Dashboard, Calendar, Analytics, Insights, Experiments, Records, Backup/Export) execute strictly read-only queries.
  - GET endpoints do not mutate data or perform implicit background writes.

## 2. Backup & Data Preservation Policy
- **Automatic Daily Backups:**
  - On application startup, Tracker takes an automatic snapshot of the SQLite database into the `backups` directory using the native SQLite Online Backup API.
  - Automatic startup backups keep a rolling history of up to 14 daily snapshots (`tracker-backup-YYYY-MM-DD-HHMMSS.db`).
- **Logical Backup & Export:**
  - Full logical backup (`/api/backup`): Downloadable `.zip` archive containing `manifest.json` and `data.json` with SHA-256 validation token signing.
  - Analytical export (`/api/export/csv`): Zip of CSV files with spreadsheet formula injection escaping (`'` prefix for leading `=`, `+`, `-`, `@`).
  - Raw JSON export (`/api/export/json`).
- **Safety Backups & Pre-Restore Bounded Retention:**
  - Before any full replacement restore operation is applied, Tracker takes a safety backup (`tracker-before-restore-*.zip`).
  - Safety archives are retained on both restore success and restore failure.
  - Upon successful restore, safety backup retention automatically keeps the 5 most recent safety archives to prevent disk space exhaustion.

## 3. Emergency Recovery Runbook
If application data becomes corrupted, or an accidental data loss occurs:

1. **Stop Writes:** Terminate the backend server or application process (`uvicorn app.main:app`).
2. **Preserve Current DB File:** Make a physical copy of `data/tracker.db` and associated `-wal` / `-shm` files to an external location for forensic investigation.
3. **Locate Latest Valid Backup:**
   - Locate the most recent daily snapshot in `data/backups/tracker-backup-*.db` or a user-created `.zip` logical backup.
   - Or locate the most recent pre-restore safety backup in `data/backups/tracker-before-restore-*.zip`.
4. **Restore Options:**
   - **Option A (Logical Restore via UI/API):** Start backend, upload valid `.zip` backup to `/api/backup/validate`, inspect summary, and execute `/api/backup/restore` with validation token and confirmation header.
   - **Option B (File-level SQLite Restore):**
     1. Stop the backend process completely.
     2. Replace `data/tracker.db` with the uncompressed snapshot `.db` file.
     3. Remove `data/tracker.db-wal` and `data/tracker.db-shm` if present.
     4. Start backend and run `alembic upgrade head` to ensure schema revision parity.
5. **Verify Data Integrity:**
   - Run `curl -s http://localhost:8000/api/ready` to ensure database connectivity and schema revision status (`"status": "ready"`).
   - Check Dashboard, Progress, and Records in the frontend.

## 6. Readiness Verdict
**READY FOR V1**
