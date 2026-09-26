"""Real SQLite/HTTP round trips, frozen v1 compatibility and destructive failures."""
import csv
import io
import json
import os
import struct
import time
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app.core.config import Settings
from app.db.models import AppMetadata
from app.main import create_app
from app.services import backup, habits
from tests.helpers import FrozenClock, run_migrations
from tests.test_records_api import seed, TODAY, MON
from tests.test_progress_api import config


@pytest.fixture
def payload():
    return json.loads((Path(__file__).parent / "fixtures/backup-v1.json").read_text(encoding="utf-8"))


def pack(payload):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in payload.items():
            archive.writestr(name + ".json", backup.json_bytes(value))
    return stream.getvalue()


def apply(client, raw):
    preview = client.post("/api/backup/validate", content=raw)
    assert preview.status_code == 200, preview.text
    return client.post("/api/backup/restore", content=raw, headers={
        "X-Tracker-Validation-Token": preview.json()["validation_token"],
        "X-Tracker-Confirm-Restore": "replace",
    })


def canonical(database):
    return json.loads(backup.json_bytes(backup.read_snapshot(database)))


def test_frozen_v1_fixture_restore(client, app, payload):
    response = apply(client, pack(payload))
    assert response.status_code == 200, response.text
    assert canonical(app.state.database) == payload["data"]
    assert client.get("/api/records").json()["summary"]["habit_completions"] == 1
    assert client.get("/api/backup").headers["content-type"] == "application/zip"


def test_roundtrip_two_databases_records_history_experiments(client, app, session, health_area, tmp_path):
    app.state.clock = FrozenClock(TODAY)
    ids = seed(session, health_area["id"])
    habits.update_habit(session, ids["habit_id"], config(health_area["id"], weight=3),
                        effective_date=MON.replace(day=14))
    source = canonical(app.state.database)
    paths = ["/api/records", "/api/progress/days/2026-09-09", "/api/progress/weeks/2026-09-14",
             f"/api/experiments/{ids['completed_id']}", f"/api/habits/{ids['habit_id']}/versions"]
    expected = {path: client.get(path).json() for path in paths}
    assert expected["/api/records"]["records"]["longest_streak"]["best_streak"] == 7
    settings_b = Settings(_env_file=None, app_env="test", data_dir=tmp_path / "database-b")
    settings_b.ensure_directories()
    run_migrations(settings_b.resolved_database_url)
    app_b = create_app(settings_b, clock=FrozenClock(TODAY))
    with TestClient(app_b) as target:
        assert apply(target, client.get("/api/backup").content).status_code == 200
        assert canonical(app_b.state.database) == source
        assert {path: target.get(path).json() for path in paths} == expected


def test_full_replace_and_safety_can_be_restored(client, app, health_area, payload):
    old = canonical(app.state.database)
    response = apply(client, pack(payload))
    assert response.status_code == 200, response.text
    assert canonical(app.state.database) == payload["data"]
    safety = app.state.settings.resolved_backups_dir / response.json()["safety_backup"]
    assert safety.is_file()
    assert apply(client, safety.read_bytes()).status_code == 200
    assert canonical(app.state.database) == old


def test_late_database_constraint_rolls_back_everything(client, app, session, health_area, payload):
    seed(session, health_area['id'])
    before = canonical(app.state.database)
    # The final table fails in the database, after every delete and other insert.
    # This is a real SQLite constraint failure, not a mocked validator exception.
    session.execute(text("CREATE TRIGGER fail_snapshot BEFORE INSERT ON insight_snapshots "
                         "BEGIN SELECT RAISE(ABORT, 'injected late constraint'); END"))
    session.commit()
    response = apply(client, pack(payload))
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "restore_failed"
    assert "injected" not in response.text
    assert canonical(app.state.database) == before
    safety = list(app.state.settings.resolved_backups_dir.glob("tracker-before-restore-*.zip"))
    assert len(safety) == 1
    assert backup.validate_archive(safety[0].read_bytes(), app.state.settings)[1].model_dump(mode="json") == before


def test_safety_write_failure_aborts_before_deletion(client, app, health_area, payload, monkeypatch):
    before = canonical(app.state.database)
    def fail(*_):
        raise OSError("disk full")
    monkeypatch.setattr(backup, "_write_safety", fail)
    assert apply(client, pack(payload)).status_code == 500
    assert canonical(app.state.database) == before


def test_download_export_headers_read_only_no_secrets(client, app, session, payload, monkeypatch):
    assert apply(client, pack(payload)).status_code == 200
    session.add(AppMetadata(key="api_token", value="secret-sentinel"))
    session.commit()
    monkeypatch.setenv("TRACKER_TELEGRAM_TOKEN", "telegram-sentinel")
    before = canonical(app.state.database)
    queries = []
    def count(_conn, _cursor, statement, *_):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)
    event.listen(app.state.database.engine, "before_cursor_execute", count)
    try:
        for path, extension, content_type in [('/api/backup', '.zip', 'application/zip'),
                ('/api/export/json', '.json', 'application/json'), ('/api/export/csv', '.zip', 'application/zip')]:
            queries.clear()
            response = client.get(path)
            assert response.status_code == 200
            assert len(queries) == 7
            assert response.headers["content-type"] == content_type
            assert response.headers["content-disposition"].endswith(extension + '"')
            assert response.headers["cache-control"] == "no-store"
            if content_type == 'application/zip':
                with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                    raw = b' '.join(archive.read(name) for name in archive.namelist())
                    if path == '/api/backup':
                        manifest = json.loads(archive.read('manifest.json'))
                        assert manifest == payload['manifest'] | {'created_at': manifest['created_at']}
                    else:
                        assert len(archive.namelist()) == 7
                        state = list(csv.DictReader(io.StringIO(archive.read('daily_states.csv').decode('utf-8-sig'))))[0]
                        assert state['energy'] == '' and state['gaming_minutes'] == '0' and state['alcohol'] == 'false'
                        assert 'Прогулка' in archive.read('habit_versions.csv').decode('utf-8-sig')
            else:
                raw = response.content
                assert response.json() == {'data': before}
            for forbidden in [b'secret-sentinel', b'telegram-sentinel', b'app_metadata', b'database_url', b'achievements']:
                assert forbidden not in raw
    finally:
        event.remove(app.state.database.engine, 'before_cursor_execute', count)
    assert canonical(app.state.database) == before


@pytest.mark.parametrize('change', [
    'future', 'old', 'format', 'schema', 'missing', 'extra', 'duplicate', 'fk', 'enum', 'date', 'range',
    'coercion', 'bool_id', 'overflow', 'counts', 'version_bool', 'null_required', 'duplicate_day',
    'duplicate_snapshot', 'history', 'missing_history', 'schedule', 'state_consistency',
    'experiment_dates', 'skip', 'timestamp_precision', 'timestamp_offset', 'snapshot_enum',
])
def test_invalid_payloads_are_rejected_without_writes(client, app, payload, change):
    data = payload['data']
    if change == 'future': payload['manifest']['version'] = 5
    elif change == 'old': payload['manifest']['version'] = 0
    elif change == 'format': payload['manifest']['format'] = 'tracker-export'
    elif change == 'schema': payload['manifest']['alembic_revision'] = 'unknown'
    elif change == 'missing': del data['experiments']
    elif change == 'extra': data['secrets'] = []
    elif change == 'duplicate': data['habits'].append(deepcopy(data['habits'][0]))
    elif change == 'fk': data['habit_versions'][0]['area_id'] = 999
    elif change == 'enum': data['habit_entries'][0]['status'] = 'other'
    elif change == 'date': data['daily_states'][0]['state_date'] = '2026-02-30'
    elif change == 'range': data['daily_states'][0]['mood'] = 6
    elif change == 'coercion': data['daily_states'][0]['mood'] = '3'
    elif change == 'bool_id': data['habits'][0]['id'] = True
    elif change == 'overflow': data['habits'][0]['id'] = 2**63
    elif change == 'counts': payload['manifest']['counts']['habits'] = 999
    elif change == 'version_bool': payload['manifest']['version'] = True
    elif change == 'null_required': data['experiments'][0]['title'] = None
    elif change == 'duplicate_day': data['habit_entries'].append(dict(data['habit_entries'][0], id=2))
    elif change == 'duplicate_snapshot': data['insight_snapshots'].append(dict(data['insight_snapshots'][0], id=2))
    elif change == 'history': data['habit_versions'][1]['version_number'] = 4
    elif change == 'missing_history': data['habit_versions'] = []
    elif change == 'schedule': data['habit_versions'][0]['schedule_weekdays'] = []
    elif change == 'state_consistency': data['daily_states'][0]['alcohol_detail'] = 'wine'
    elif change == 'experiment_dates': data['experiments'][0]['end_date'] = '2025-01-01'
    elif change == 'skip': data['habit_entries'][0]['status'] = 'skipped'
    elif change == 'timestamp_precision': data['habits'][0]['created_at'] += '7'
    elif change == 'timestamp_offset': data['habits'][0]['created_at'] += '+03:00'
    elif change == 'snapshot_enum': data['insight_snapshots'][0]['confidence'] = 'certain'
    if change != 'counts':
        payload['manifest']['counts'] = {name: len(rows) for name, rows in data.items()}
    before = canonical(app.state.database)
    response = client.post('/api/backup/validate', content=pack(payload))
    assert response.status_code == 422, response.text
    if change == 'future': assert 'более новой' in response.json()['error']['message']
    assert canonical(app.state.database) == before
    assert not app.state.settings.resolved_backups_dir.exists()


@pytest.mark.parametrize('kind', ['invalid_zip', 'invalid_json', 'missing_manifest', 'traversal', 'duplicate_name', 'duplicate_json', 'nan', 'crc'])
def test_corrupt_and_unsafe_archives(client, payload, kind):
    if kind == 'invalid_zip': raw = b'not a ZIP'
    else:
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
            manifest_name = '../manifest.json' if kind == 'traversal' else 'data.json' if kind == 'duplicate_name' else 'other.json' if kind == 'missing_manifest' else 'manifest.json'
            manifest = backup.json_bytes(payload['manifest'])
            if kind == 'duplicate_json': manifest = manifest.replace(b'"version": 1', b'"version": 1, "version": 1')
            archive.writestr(manifest_name, manifest)
            data = b'{' if kind == 'invalid_json' else backup.json_bytes(payload['data'])
            if kind == 'nan': data = data.replace(b'0.9', b'NaN')
            archive.writestr('data.json', data)
        raw = output.getvalue()
        if kind == 'crc': raw = raw.replace(b'tracker-backup', b'tracker-broken')
    assert client.post('/api/backup/validate', content=raw).status_code == 422


def test_limits(client, app, payload):
    raw = pack(payload)
    app.state.settings.backup_max_upload_bytes = 1024
    assert client.post('/api/backup/validate', content=raw).status_code == 413
    # Chunked upload must be bounded even without Content-Length.
    assert client.post('/api/backup/validate', content=iter([raw[:800], raw[800:]])).status_code == 413
    app.state.settings.backup_max_upload_bytes = 64 * 1024 * 1024
    app.state.settings.backup_max_uncompressed_bytes = 1024
    assert client.post('/api/backup/validate', content=raw).status_code == 422


def test_restore_confirmation_token_and_file_binding(client, app, payload):
    raw = pack(payload)
    preview = client.post('/api/backup/validate', content=raw).json()
    token = preview['validation_token']
    for headers in [{}, {'X-Tracker-Confirm-Restore': 'replace'}, {'X-Tracker-Validation-Token': token},
                    {'X-Tracker-Confirm-Restore': 'replace', 'X-Tracker-Validation-Token': 'invalid'},
                    {'X-Tracker-Confirm-Restore': 'replace', 'X-Tracker-Validation-Token': backup.validation_token(raw, app.state.backup_signing_key, issued=int(time.time()) - 1900)}]:
        assert client.post('/api/backup/restore', content=raw, headers=headers).status_code == 422
    payload['data']['areas'][0]['name'] = 'Другой файл'
    assert client.post('/api/backup/restore', content=pack(payload), headers={
        'X-Tracker-Confirm-Restore': 'replace', 'X-Tracker-Validation-Token': token}).status_code == 422
    assert canonical(app.state.database)['areas'] == []


def test_csv_formula_safety_and_empty_tables(payload):
    payload['data']['areas'][0]['name'] = '=1+1'
    payload['data']['experiments'] = []
    with zipfile.ZipFile(io.BytesIO(backup.csv_archive(payload['data']))) as archive:
        assert "'=1+1" in archive.read('areas.csv').decode('utf-8-sig')
        assert len(archive.read('experiments.csv').decode('utf-8-sig').splitlines()) == 1


def test_every_domain_table_and_column_accounted_for():
    from app.db.base import Base
    from app.schemas.backup import BackupDataV1
    assert set(Base.metadata.tables) == {table.name for table in backup.TABLES.values()} | {'app_metadata'}
    for section, table in backup.TABLES.items():
        row_type = BackupDataV1.model_fields[section].annotation.__args__[0]
        assert set(row_type.model_fields) == set(table.c.keys())


def test_empty_backup_can_replace_and_restore_existing_history(client, app, session, health_area, payload):
    seed(session, health_area['id'])
    old = canonical(app.state.database)
    payload['data'] = {name: [] for name in backup.TABLES}
    payload['manifest']['counts'] = {name: 0 for name in backup.TABLES}
    response = apply(client, pack(payload))
    assert response.status_code == 200, response.text
    assert all(not rows for rows in canonical(app.state.database).values())
    safety = app.state.settings.resolved_backups_dir / response.json()['safety_backup']
    assert apply(client, safety.read_bytes()).status_code == 200
    assert canonical(app.state.database) == old


def test_forged_zip_entry_count_is_rejected_before_zipinfo_allocation(client, payload, monkeypatch):
    payload['extra'] = {}
    raw = bytearray(pack(payload))
    eocd = raw.rfind(b'PK\x05\x06')
    struct.pack_into('<2H', raw, eocd + 8, 2, 2)
    def must_not_open(*_, **__):
        pytest.fail('Archive directory was not bounded before parsing')
    monkeypatch.setattr(backup.zipfile, 'ZipFile', must_not_open)
    assert client.post('/api/backup/validate', content=bytes(raw)).status_code == 422


def test_safety_backups_are_pruned(client, app, payload):
    backups_dir = app.state.settings.resolved_backups_dir
    backups_dir.mkdir(parents=True, exist_ok=True)
    # Create 7 dummy safety backup files with increasing timestamps.
    old_files = []
    for index in range(7):
        file_path = backups_dir / f"tracker-before-restore-2026-01-{index+1:02d}T100000-{index}.zip"
        file_path.write_bytes(b"dummy safety backup")
        # Ensure distinct mtimes
        os.utime(file_path, (1700000000 + index * 10, 1700000000 + index * 10))
        old_files.append(file_path)

    response = apply(client, pack(payload))
    assert response.status_code == 200, response.text

    remaining_safety = list(backups_dir.glob("tracker-before-restore-*.zip"))
    assert len(remaining_safety) == 5
    assert not old_files[0].exists()
    assert not old_files[1].exists()
    assert not old_files[2].exists()


def test_openapi_binary_upload_and_download_contract(client):
    paths = client.get('/api/openapi.json').json()['paths']
    for path in ['/api/backup/validate', '/api/backup/restore']:
        assert paths[path]['post']['requestBody']['content']['application/zip']['schema']['format'] == 'binary'
    assert 'application/zip' in paths['/api/backup']['get']['responses']['200']['content']
