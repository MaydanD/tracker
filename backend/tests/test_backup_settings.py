"""Real persistence and official ZIP with a fake HTTPS connection; no network."""
import io
import json
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest

from app.services import backup, backup_settings as service, telegram_backup as telegram
from tests.helpers import FrozenClock

TOKEN = '123456789:' + 'a' * 32


@pytest.fixture
def transport(monkeypatch):
    class FakeHTTPS:
        calls = []
        code = 200
        fail = False
        # When set, the raw response body is sent instead of a JSON envelope,
        # so tests can reproduce a rejection Telegram answers without JSON.
        body = None
        def __init__(self, host, timeout):
            assert host == 'api.telegram.org' and timeout == 45
        def request(self, method, path, body, headers):
            if self.fail:
                raise OSError('secret-bearing ' + TOKEN)
            self.calls.append((path.rsplit('/', 1)[1], body, headers))
        def getresponse(self):
            return self
        @property
        def status(self):
            return self.code
        def read(self, limit):
            if self.body is not None:
                return self.body
            return json.dumps({'ok': self.code == 200, 'error_code': self.code,
                               'description': TOKEN, 'result': {'type': 'private', 'id': 123}}).encode()
        def close(self):
            pass
    monkeypatch.setattr(telegram.http.client, 'HTTPSConnection', FakeHTTPS)
    return FakeHTTPS


def configure(client, auto=False):
    response = client.put('/api/backup/settings', json={'token': TOKEN, 'chat_id': '123', 'auto_enabled': auto})
    assert response.status_code == 200, response.text
    return response


def status(client):
    return client.get('/api/backup/settings').json()


def test_monthly_download_and_next_month(client, app):
    app.state.clock = FrozenClock(date(2026, 10, 8))
    assert status(client)['reminder_due']
    assert client.get('/api/backup').status_code == 200
    assert not status(client)['reminder_due']
    assert status(client)['last_backup_kind'] == 'download'
    app.state.clock = FrozenClock(date(2026, 11, 8))
    assert status(client)['reminder_due']


def test_generation_failure_does_not_record_success(client, app, monkeypatch):
    def fail(*_):
        raise telegram.TelegramError('Ошибка создания архива')
    monkeypatch.setattr(backup, 'make_archive', fail)
    assert client.get('/api/backup').status_code == 502
    assert status(client)['last_successful_backup_at'] is None
    configure(client)
    assert client.post('/api/backup/telegram/send').status_code == 502
    assert status(client)['last_successful_backup_at'] is None


def test_secret_is_not_in_api_database_or_any_backup(client, app, transport, caplog):
    response = configure(client)
    assert TOKEN not in response.text
    assert response.json()['token_saved']
    assert TOKEN not in client.get('/api/backup/settings').text
    with app.state.database.session() as session:
        assert TOKEN not in json.dumps(service.read(session))
    raw = client.get('/api/backup').content
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert TOKEN.encode() not in b''.join(archive.read(name) for name in archive.namelist())
    assert TOKEN not in caplog.text


def test_connection_checks_token_and_chat_without_upload(client, transport):
    configure(client)
    result = client.post('/api/backup/telegram/check')
    assert result.status_code == 200 and result.json()['connected']
    # sendChatAction(typing) replaced sendMessage — no visible message in chat.
    assert [call[0] for call in transport.calls] == ['getMe', 'getChat', 'sendChatAction']
    # The write-access probe must carry only the action field: no document, no
    # caption, no message text that could end up in the user's chat.
    _, body, _ = transport.calls[-1]
    assert b'name="action"' in body and b'typing' in body
    assert b'name="document"' not in body and b'filename="' not in body and b'caption' not in body
    assert status(client)['reminder_due']


def test_wire_format_is_valid_multipart_and_getme_sends_no_empty_body(client, transport):
    """Regression: a field-less getMe must not be sent as an empty multipart body.

    Telegram answers an empty multipart body with 400 *and no body*, which the
    transport used to report as a network failure — so every real check failed.
    """
    configure(client)
    transport.calls.clear()
    assert client.post('/api/backup/telegram/check').status_code == 200

    getme_method, getme_body, getme_headers = transport.calls[0]
    assert getme_method == 'getMe'
    assert getme_body == b'', 'a field-less method must not send an empty multipart body'
    assert 'Content-Type' not in getme_headers

    for method, body, headers in transport.calls[1:]:
        assert 'multipart/form-data' in headers['Content-Type']
        # Every part must be complete: at least one part plus the closing boundary.
        assert body.startswith(b'--') and body.endswith(b'--\r\n')
        assert b'Content-Disposition: form-data; name=' in body

    # The document upload keeps both its fields and its file part.
    transport.calls.clear()
    assert client.post('/api/backup/telegram/send').status_code == 200
    method, body, headers = transport.calls[0]
    assert method == 'sendDocument'
    assert b'name="document"; filename="tracker-backup-' in body
    assert body.endswith(b'--\r\n') and headers['Content-Type'].startswith('multipart/form-data')


def test_rejection_without_json_is_not_reported_as_silence(client, transport):
    """A Telegram 400 with an empty body must not masquerade as 'no answer'."""
    configure(client)
    transport.code = 400
    transport.body = b''
    response = client.post('/api/backup/telegram/check')
    assert response.status_code == 502
    message = response.json()['error']['message']
    assert 'не ответил' not in message.lower(), message
    assert 'отклонил' in message.lower(), message
    assert TOKEN not in response.text


def test_sent_document_is_exact_official_zip_and_restores(client, app, transport, monkeypatch):
    configure(client)
    generated = []
    original = backup.make_archive
    def capture(*args):
        raw = original(*args)
        generated.append(raw)
        return raw
    monkeypatch.setattr(backup, 'make_archive', capture)
    response = client.post('/api/backup/telegram/send')
    assert response.status_code == 200
    assert response.json()['last_backup_kind'] == 'telegram'
    assert not response.json()['reminder_due']
    method, body, headers = transport.calls[0]
    assert method == 'sendDocument'
    raw = generated[0]
    assert raw in body
    assert 'multipart/form-data' in headers['Content-Type']
    backup.validate_archive(raw, app.state.settings)
    preview = client.post('/api/backup/validate', content=raw).json()
    restore = client.post('/api/backup/restore', content=raw, headers={
        'X-Tracker-Validation-Token': preview['validation_token'], 'X-Tracker-Confirm-Restore': 'replace'})
    assert restore.status_code == 200


@pytest.mark.parametrize('code', [400, 401, 403, 404, 429, 500])
def test_telegram_errors_are_safe_and_do_not_count(client, transport, caplog, code):
    configure(client)
    transport.code = code
    response = client.post('/api/backup/telegram/send')
    assert response.status_code == 502
    assert TOKEN not in response.text + caplog.text
    assert status(client)['last_successful_backup_at'] is None
    assert status(client)['last_error']
    assert status(client)['reminder_due']


def test_timeout_does_not_leak_secret(client, transport, caplog):
    configure(client)
    transport.fail = True
    response = client.post('/api/backup/telegram/check')
    assert response.status_code == 502
    assert TOKEN not in response.text + caplog.text


@pytest.mark.parametrize('payload', [{'token': 'bad'}, {'token': ['secret']}, {'chat_id': '-123'}, {'auto_enabled': True}, {'token': TOKEN, 'extra': TOKEN}])
def test_invalid_settings_never_echo_input(client, payload):
    response = client.put('/api/backup/settings', json=payload)
    assert response.status_code == 422
    assert TOKEN not in response.text and 'secret' not in response.text


def test_auto_once_across_restarts_and_next_month(client, app, transport):
    configure(client, auto=True)
    for _ in range(3):
        assert client.post('/api/backup/auto').status_code == 200
    assert len(transport.calls) == 1
    assert status(client)['last_backup_kind'] == 'auto-telegram'
    from app.main import create_app
    from fastapi.testclient import TestClient
    with TestClient(create_app(app.state.settings, clock=app.state.clock)) as other:
        other.post('/api/backup/auto')
    assert len(transport.calls) == 1
    app.state.clock = FrozenClock(date(2026, 12, 8))
    client.post('/api/backup/auto')
    assert len(transport.calls) == 2


def test_download_suppresses_auto_and_failure_has_persistent_backoff(client, app, transport):
    configure(client, auto=True)
    client.get('/api/backup')
    client.post('/api/backup/auto')
    assert not transport.calls
    app.state.clock = app.state.clock.advance(35)
    transport.code = 500
    for _ in range(5):
        client.post('/api/backup/auto')
    assert len(transport.calls) == 1
    assert status(client)['reminder_due'] and status(client)['last_error']
    app.state.clock = app.state.clock.advance(1)
    transport.code = 200
    client.post('/api/backup/auto')
    assert len(transport.calls) == 2
    assert not status(client)['reminder_due']


def test_concurrent_trigger_claim_blocks_manual_and_other_app(client, app, transport, monkeypatch):
    configure(client, auto=True)
    entered, release = threading.Event(), threading.Event()
    original = telegram.send
    def slow(*args):
        entered.set()
        assert release.wait(5)
        original(*args)
    monkeypatch.setattr(telegram, 'send', slow)
    from app.db.database import create_database
    other_database = create_database(app.state.settings)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(service.perform, app.state.database, app.state.settings, app.state.clock, automatic=True)
        assert entered.wait(5)
        try:
            assert status(client)['in_progress']
            assert client.post('/api/backup/telegram/send').status_code == 409
            service.perform(other_database, app.state.settings, app.state.clock, automatic=True)
        finally:
            release.set()
        future.result()
    other_database.dispose()
    assert len(transport.calls) == 1
    assert not status(client)['reminder_due']

@pytest.mark.parametrize('path', ['/api/backup/auto', '/api/backup/telegram/send', '/api/backup/telegram/check'])
def test_cross_site_cannot_trigger_telegram(client, transport, path):
    configure(client, auto=True)
    assert client.post(path, headers={'Origin': 'https://untrusted.example'}).status_code == 403
    assert not transport.calls


def test_local_month_not_utc_month(client, app):
    from datetime import datetime, timezone, timedelta
    class Midnight:
        def today(self):
            return date(2026, 10, 1)
        def now(self):
            return datetime(2026, 10, 1, 0, 30, tzinfo=timezone(timedelta(hours=3)))
    app.state.clock = Midnight()
    client.get('/api/backup')
    assert status(client)['last_successful_backup_at'].startswith('2026-09-30')
    assert not status(client)['reminder_due']


def test_physical_sqlite_copy_has_no_token(client, app, tmp_path):
    from app.db.backup import copy_sqlite_database
    configure(client)
    destination = tmp_path / 'physical.db'
    copy_sqlite_database(app.state.settings.resolved_database_path, destination)
    assert TOKEN.encode() not in destination.read_bytes()


def test_check_rejects_non_private_chat(client, monkeypatch):
    configure(client)
    monkeypatch.setattr(telegram, 'call', lambda *_, **__: {'type': 'group'})
    response = client.post('/api/backup/telegram/check')
    assert response.status_code == 502
    assert 'личного чата' in response.json()['error']['message']


def test_crash_claim_survives_app_restart_and_auto_waits_one_day(client, app, transport):
    configure(client, auto=True)
    with service.locked(app.state.database) as state:
        state.update(claim='crashed-worker', claim_until=service.now(app.state.clock).timestamp() + 600,
                     next_auto_attempt_at=(service.now(app.state.clock) + __import__('datetime').timedelta(days=1)).isoformat())
    client.post('/api/backup/auto')
    assert not transport.calls
    assert status(client)['reminder_due']
    app.state.clock = app.state.clock.advance(1)
    client.post('/api/backup/auto')
    assert len(transport.calls) == 1


# ---------------------------------------------------------------------------
# Regression tests: Telegram connection status semantics
# ---------------------------------------------------------------------------

def test_status_not_configured_without_credentials(client):
    """No token file, no chat_id → configured=False, verified=False."""
    s = status(client)
    assert not s['configured']
    assert not s['verified']
    assert s['telegram_verified_at'] is None
    assert not s['connected']


def test_status_configured_after_save(client, transport):
    """token saved + chat_id present → configured=True, but not yet verified."""
    configure(client)
    s = status(client)
    assert s['configured']
    assert not s['verified']
    assert s['telegram_verified_at'] is None
    assert not s['connected']


def test_verification_success_sets_verified_and_persists(client, transport):
    """Successful check → connected=True, verified=True, telegram_verified_at set."""
    configure(client)
    result = client.post('/api/backup/telegram/check')
    assert result.status_code == 200
    s = result.json()
    assert s['connected']
    assert s['verified']
    assert s['telegram_verified_at'] is not None
    # Persists across a fresh status fetch (simulates page reload).
    reloaded = status(client)
    assert reloaded['verified']
    assert reloaded['telegram_verified_at'] == s['telegram_verified_at']


def test_verification_failure_does_not_set_verified(client, transport):
    """Failed check → connected=False, verified=False, last_error set."""
    configure(client)
    transport.code = 403
    result = client.post('/api/backup/telegram/check')
    assert result.status_code == 502
    s = status(client)
    assert not s['connected']
    assert not s['verified']
    assert s['telegram_verified_at'] is None
    assert s['last_error']


def test_successful_send_sets_verified(client, transport):
    """Successful sendDocument → verified=True, telegram_verified_at set."""
    configure(client)
    result = client.post('/api/backup/telegram/send')
    assert result.status_code == 200
    s = result.json()
    assert s['connected']
    assert s['verified']
    assert s['telegram_verified_at'] is not None
    assert s['last_backup_kind'] == 'telegram'


def test_verified_state_survives_reload(client, transport):
    """After successful send, a fresh GET /backup/settings still shows verified."""
    configure(client)
    client.post('/api/backup/telegram/send')
    reloaded = status(client)
    assert reloaded['verified']
    assert reloaded['telegram_verified_at'] is not None
    assert reloaded['connected']


def test_failed_send_does_not_set_verified(client, transport):
    """Failed sendDocument → verified=False, telegram_verified_at stays None."""
    configure(client)
    transport.code = 400
    result = client.post('/api/backup/telegram/send')
    assert result.status_code == 502
    s = status(client)
    assert not s['verified']
    assert s['telegram_verified_at'] is None
    assert not s['connected']


def test_new_token_clears_verified(client, transport):
    """Re-saving settings with a new token resets verified and telegram_verified_at."""
    configure(client)
    client.post('/api/backup/telegram/send')
    assert status(client)['verified']
    # Save again with a new token (same chat_id) — verified must be cleared.
    new_token = '987654321:' + 'b' * 32
    response = client.put('/api/backup/settings', json={'token': new_token, 'chat_id': '123', 'auto_enabled': False})
    assert response.status_code == 200
    s = response.json()
    assert not s['connected']
    assert not s['verified']
    assert s['telegram_verified_at'] is None


def test_token_not_returned_to_frontend(client, transport):
    """The token must never appear in any API response body."""
    configure(client)
    client.post('/api/backup/telegram/check')
    client.post('/api/backup/telegram/send')
    for path in ['/api/backup/settings', '/api/backup/telegram/check', '/api/backup/telegram/send']:
        resp = client.get(path) if path == '/api/backup/settings' else client.post(path)
        assert TOKEN not in resp.text


def test_same_credentials_save_does_not_clear_verified(client, transport):
    """Re-saving with the exact same token and chat_id must NOT reset verified."""
    configure(client)
    client.post('/api/backup/telegram/send')
    assert status(client)['verified']
    verified_at_before = status(client)['telegram_verified_at']
    # Save exactly the same token and chat_id again.
    response = client.put('/api/backup/settings', json={'token': TOKEN, 'chat_id': '123', 'auto_enabled': False})
    assert response.status_code == 200
    s = response.json()
    # Verification must survive an identical save.
    assert s['verified'], "Saving the same credentials must not clear verified status"
    assert s['telegram_verified_at'] == verified_at_before


def test_changed_chat_id_clears_verified(client, transport):
    """A real chat_id change must reset verification, even with the same token."""
    configure(client)
    client.post('/api/backup/telegram/send')
    assert status(client)['verified']
    # Same token, different chat_id — this is a real credential change.
    response = client.put('/api/backup/settings', json={'token': TOKEN, 'chat_id': '456', 'auto_enabled': False})
    assert response.status_code == 200
    s = response.json()
    assert not s['connected']
    assert not s['verified']
    assert s['telegram_verified_at'] is None


def test_save_without_token_keeps_stored_token_and_verified(client, transport):
    """Omitting the token (masked/unchanged) keeps the secret and verification."""
    configure(client)
    client.post('/api/backup/telegram/send')
    verified_at = status(client)['telegram_verified_at']
    assert verified_at
    # No token field at all — the contract for "keep the existing token".
    response = client.put('/api/backup/settings', json={'chat_id': '123', 'auto_enabled': True})
    assert response.status_code == 200
    s = response.json()
    assert s['token_saved'] and s['configured']
    assert s['verified'] and s['telegram_verified_at'] == verified_at
    assert TOKEN not in response.text


def test_check_timeout_error_message_does_not_mention_backup_send(client, transport):
    """A network failure during check must not suggest the 'отправка' may have completed."""
    configure(client)
    transport.fail = True
    response = client.post('/api/backup/telegram/check')
    assert response.status_code == 502
    msg = response.json()['error']['message']
    assert 'отправка' not in msg.lower(), f"Check error must not mention backup send: {msg!r}"
    assert TOKEN not in msg


def test_auto_check_does_not_retry_storm(client, app, transport):
    """Repeated auto triggers within the backoff window must not cause multiple calls."""
    configure(client, auto=True)
    # Simulate a failed auto send setting a next_auto_attempt_at in the future.
    import datetime
    future = (service.now(app.state.clock) + datetime.timedelta(days=1)).isoformat()
    with service.locked(app.state.database) as state:
        state['next_auto_attempt_at'] = future
    calls_before = len(transport.calls)
    for _ in range(5):
        client.post('/api/backup/auto')
    assert len(transport.calls) == calls_before, "Auto check must not fire during backoff window"
