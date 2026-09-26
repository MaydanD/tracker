# Backup / Export / Restore — Stage 12

Official portable backup format: **`tracker-backup`, version 1**. Settings at
`/#/settings` provides downloads, validation and full replacement. No migration:
Alembic remains `c3f1a7b24d90`. No new dependency or persistence table.

## Format and inventory

A UTF-8 ZIP contains **exactly** `manifest.json` and `data.json`.
The manifest is:

```json
{
  "format": "tracker-backup",
  "version": 1,
  "created_at": "2026-09-26T16:00:00",
  "alembic_revision": "c3f1a7b24d90",
  "application_backup_version": 1,
  "counts": {
    "areas": 1,
    "habits": 1,
    "habit_versions": 2,
    "habit_entries": 1,
    "daily_states": 1,
    "experiments": 1,
    "insight_snapshots": 1
  }
}
```

`data.json` has those seven required arrays, including empty arrays:

| Section | Table | Preserved source data |
|---|---|---|
| areas | areas | IDs, names, colours, lifecycle, timestamps |
| habits | habits | Stable identity, archive status and timestamps |
| habit_versions | habit_versions | Every version, effective date, weight, area, mode, unit, schedule |
| habit_entries | daily_habit_entries | IDs/FKs, dates, statuses, exact millionths, skip reasons, notes, timestamps |
| daily_states | daily_states | All observations, nulls, false/zero distinctions, notes and timestamps |
| experiments | experiments | IDs, title, hypothesis, protocol, planned dates, cancellation, timestamps |
| insight_snapshots | insight_snapshots | Fingerprints, evaluation dates, evidence and policy versions, labels, timestamps |

Rows are ordered by ID; sections and columns have a fixed order. Dates use
`YYYY-MM-DD`, datetimes use ISO `T` with at most six fractional digits. Naive
datetimes mean UTC, matching SQLite storage; `Z`/`+00:00` are accepted as UTC.
Other offsets and finer-than-microsecond timestamps are rejected rather than
silently truncated. Null stays null. Quantities remain integer millionths (e.g.
6.4 km = `6400000`); persisted snapshot floats round-trip as Python/SQLite floats.
The frontend downloads binary blobs without parsing source integers through JS.

Excluded: derived Records/Achievements, streaks, Dashboard/analytics aggregates,
Owl state and browser dismiss/cooldown state. Also excluded: `app_metadata`
(infrastructure bookkeeping only), `alembic_version` rows, settings, environment,
database URLs, filesystem paths, server/session/API/Telegram/OAuth secrets.
The schema revision alone is included as format provenance. User-authored free
text is preserved verbatim; users should treat their downloaded history as private.

`schemas/backup.py` pins the v1 contract explicitly, independent of ORM evolution.
`NORMALIZERS` dispatches by version into the current restore DTO. Currently only
v1 with the above revision is supported. Future versions fail with
«Резервная копия создана более новой версией Tracker.» Unknown revisions fail
explicitly; never stamp or migrate the running database from archive metadata.
Future changes must add a normalizer and retain the frozen fixture test.

## API and confirmation

| Method | Route | Result |
|---|---|---|
| GET | `/api/backup` | Download official ZIP |
| GET | `/api/export/json` | Readable source tables under `data`, no restore metadata |
| GET | `/api/export/csv` | ZIP with seven independent CSV files |
| POST | `/api/backup/validate` | Manifest/count preview and `validation_token` |
| POST | `/api/backup/restore` | Full replacement, counts and safety filename |

POST bodies are raw ZIP bytes, `Content-Type: application/zip`, **not** base64 or
multipart. Restore requires `X-Tracker-Confirm-Restore: replace` and
`X-Tracker-Validation-Token` from a successful preview of those exact bytes.
The HMAC token is bound to SHA-256 of the entire archive and expires after 30
minutes. Restarting the backend invalidates tokens. There is no server-side
upload history or stored pending file; cancelling the preview requires no cleanup.
Tokens are not authentication and can be reused within their validity window;
this remains a single-process local personal application.

The UI shows all seven counts, date, format version and schema; warns that current
data will be replaced; then asks for a separate «Да, восстановить». Changing the
file invalidates the preview immediately, including in-flight validation responses.
On success, the entire app reloads to discard all component data and pending reads;
a one-time success message remains in Settings with a link to Dashboard.
Validation errors explain the field or rule without returning input values or a
traceback. A network disconnect during restore has an uncertain outcome: reconnect
and inspect data before retrying. A server-reported restore failure rolls back.

## Validation and safety limits

Validation writes nothing. Strict DTOs reject missing/extra fields, coercions,
invalid types/enums/dates, integer overflow, nonfinite floats and wrong ranges.
Cross-row checks cover duplicate IDs and composite keys, foreign keys, required
configuration history, ordered version numbers, lifecycle consistency, schedules,
daily-state contradictions, experiment windows and snapshot periods/orientation.
Historical observations are not rejected merely because the system clock changed.
Same-day configuration edits may change a habit mode after an entry was saved;
restore preserves that original quantity instead of reinterpreting it.

ZIP rules: exactly two allowlisted filenames, no directory extraction, traversal,
duplicates, symlinks, encryption, unsupported compression or ZIP64. Both CRCs are
read and checked. Duplicate JSON keys and nonstandard NaN/Infinity are rejected.
Central-directory entry counts are bounded before creating `ZipInfo` objects.
Limits apply to declared **and actual** expanded size; upload is checked while
streaming, even without `Content-Length`.

| Environment setting | Default |
|---|---|
| `TRACKER_BACKUP_MAX_UPLOAD_BYTES` | 67108864 (64 MiB compressed) |
| `TRACKER_BACKUP_MAX_UNCOMPRESSED_BYTES` | 268435456 (256 MiB expanded JSON) |

Increase both deliberately for a larger history. Full-history data, DTOs and ZIP
are held in memory; memory use can exceed the JSON size. Downloads are not capped
by the import limits, so importing a larger generated backup requires increasing
the receiving installation's limits. This is bounded import, not a streaming
multi-gigabyte archive service. No arbitrary compression-ratio cutoff rejects
legitimate highly repetitive history.

## Atomic replacement and safety copy

The backend revalidates the bytes at restore time, then uses one SQLite
`BEGIN IMMEDIATE` transaction. It holds the write reservation while reading the
current seven tables and writing a safety ZIP. The ZIP is written to an exclusive
temporary filename, flushed/fsynced, and atomically renamed before deleting rows.
Failure to write it aborts restoration without deleting anything.

Safety copies live in `<data dir>/backups/` as
`tracker-before-restore-<UTC timestamp>-<random UUID>.zip`. They are ordinary v1
backups and can be restored through the same UI. They are retained on success and
failure; no automatic deletion or safety-copy history table. Users manage these
files locally. They are separate from the existing Stage 3 startup SQLite copies
and are not subject to that copy mechanism's retention pattern.

Delete order is the reverse of the table list; insert order is areas → habits →
versions → entries → daily states → experiments → snapshots. FK enforcement stays
enabled. Explicit IDs and all timestamps are inserted in batches of 1000; there
is exactly one commit. Any insert/constraint/commit failure rolls back all deletes
and inserts. SQLite transaction recovery remains responsible for process crashes;
the extra logical copy is not a substitute for off-device backups or hardware
durability. Infrastructure metadata and Alembic version are left untouched.

Backup and exports use one explicit read transaction spanning seven ordered Core
SELECTs (no ORM eager loads, no N+1 or query per day/habit). Serialization is linear;
validation groups/sorts versions and uses binary search for entry date lookup.
ZIP timestamps and manifest creation time need not be byte-identical; canonical
persistent data must be identical after a round trip.

## Export conventions

JSON and CSV are read-only analytical exports, not restorable backup containers.
CSV ZIP: `areas.csv`, `habits.csv`, `habit_versions.csv`, `habit_entries.csv`,
`daily_states.csv`, `experiments.csv`, `insight_snapshots.csv`.
Each uses UTF-8 BOM (for Russian spreadsheet compatibility), headers even when
empty, comma delimiters, standard quoting, ISO dates, `true`/`false`, and empty
cells for null. Zero stays `0`. Arrays are JSON in a cell. Exact quantities use
the explicitly named `quantity_value_micro` column; divide by 1,000,000 and obtain
the unit from the configuration effective on that date.
Text starting with spreadsheet formula prefixes `= + - @` after whitespace is
prefixed with an apostrophe; JSON/backup retains original text. CSV empty text and
null are intentionally indistinguishable. No derived metrics or `.xlsx` output.
All downloads set safe fixed filenames, appropriate MIME, attachment disposition,
`Cache-Control: no-store`, and `X-Content-Type-Options: nosniff`.

## Verification and scope

`tests/fixtures/backup-v1.json` is a committed, frozen logical fixture (wrapped as
ZIP only by tests). It includes all seven entities, two historical configurations,
exact quantity, nullable state, cancelled experiment and a high-precision snapshot.
Do not regenerate it when adding a new backup version.

Integration coverage includes two migrated databases, canonical source equality,
records/achievements and historical daily/weekly/experiment result equality,
replacement over existing data, restorable safety copies, and an actual SQLite
trigger failure on the last inserted table proving rollback after destructive
work. Tests cover corrupt archives, validation, limits, file-bound confirmations,
seven-query read-only exports, metadata/secret exclusion and frontend flows.

Deferred: merge/selective restore, cloud or scheduled logical backups, encryption,
passwords, cross-user sync, `.xlsx`, packaging and remote disaster recovery.
Stage 12 does not introduce any of these or change the existing startup backup.
