"""Persistent monthly bookkeeping; short SQLite claims across tabs/processes.

The secret lives outside SQLite, so neither logical ZIPs nor physical startup
copies carry it. Only this module reads it. No secret values enter SQL or logs.
"""
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import UTC, timedelta

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert

from app.db.models import AppMetadata
from app.services import backup, telegram_backup
from app.services.telegram_backup import TelegramError

KEY = "backup_settings_v1"
DEFAULTS = {"last_successful_backup_at": None, "last_successful_month": None,
            "last_backup_kind": None, "last_telegram_backup_at": None,
            "chat_id": "", "auto_enabled": False, "connected": False,
            "last_error": None, "next_auto_attempt_at": None,
            "claim": None, "claim_until": 0, "manual_after": 0,
            "telegram_verified_at": None}


def read(session):
    row = session.get(AppMetadata, KEY)
    return DEFAULTS | (json.loads(row.value) if row else {})


def write(session, state):
    statement = insert(AppMetadata).values(key=KEY, value=json.dumps(state))
    session.execute(statement.on_conflict_do_update(index_elements=["key"],
                    set_={"value": statement.excluded.value, "updated_at": statement.excluded.updated_at}))


@contextmanager
def locked(database):
    with database.session() as session:
        session.execute(text("BEGIN IMMEDIATE"))
        state = read(session)
        yield state
        write(session, state)
        session.commit()


def secret_path(settings):
    return settings.resolved_data_dir / "telegram-token.secret"


def secret(settings):
    try:
        return secret_path(settings).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError:
        raise TelegramError("Не удалось прочитать сохранённый токен Telegram.") from None


def now(clock):
    return clock.now().astimezone(UTC)


def due(state, clock):
    return state["last_successful_month"] != clock.today().strftime("%Y-%m")


def status(database, settings, clock):
    with database.session() as session:
        state = read(session)
    saved = secret_path(settings).is_file()
    configured = saved and bool(state["chat_id"])
    # connected=True means the last explicit check or send succeeded for the
    # current credentials.  telegram_verified_at is a persistent ISO timestamp
    # of that event so the UI can show "verified" even after a page reload.
    # When credentials change, both fields are reset (see save()).
    verified_at = state.get("telegram_verified_at")
    verified = configured and bool(verified_at)
    return {key: state[key] for key in (
        "last_successful_backup_at", "last_backup_kind", "last_telegram_backup_at",
        "chat_id", "auto_enabled", "connected", "last_error", "next_auto_attempt_at",
    )} | {"token_saved": saved, "configured": configured,
         "telegram_verified_at": verified_at, "verified": verified,
         "reminder_due": due(state, clock), "in_progress": state["claim_until"] > now(clock).timestamp()}


def save(database, settings, clock, payload):
    # Validate manually: FastAPI/Pydantic validation details otherwise echo input.
    if not isinstance(payload, dict) or set(payload) - {"token", "chat_id", "auto_enabled"}:
        raise TelegramError("Некорректные настройки Telegram.", status_code=422)
    token = payload.get("token")
    chat = payload.get("chat_id", "")
    enabled = payload.get("auto_enabled", False)
    valid_token = token is None or (isinstance(token, str) and re.fullmatch(r"\d{5,20}:[A-Za-z0-9_-]{20,100}", token))
    valid_chat = isinstance(chat, str) and re.fullmatch(r"[1-9]\d{0,19}|", chat)
    if not valid_token or not valid_chat or type(enabled) is not bool:
        raise TelegramError("Проверьте токен бота и числовой идентификатор личного чата.", status_code=422)
    with locked(database) as state:
        if state["claim_until"] > now(clock).timestamp():
            raise TelegramError("Дождитесь завершения текущей операции.", status_code=409)
        if enabled and not (chat and (token or secret_path(settings).is_file())):
            raise TelegramError("Сначала укажите токен и идентификатор чата.", status_code=422)
        # Read the previous token *before* overwriting it: the file on disk is
        # the only source of truth for "same credentials", and comparing after
        # the write would always report "unchanged".  A request without a token
        # (the frontend never echoes the masked value back) keeps the stored one
        # and therefore never counts as a credential change.
        existing_token = secret(settings)
        if token:
            path = secret_path(settings)
            temporary = path.with_suffix(".secret.tmp")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(token)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            except OSError:
                raise TelegramError("Не удалось сохранить токен на этом устройстве.") from None
        # Only reset verification when credentials actually change.  Re-submitting
        # the same token (same bytes) or the same chat_id must not wipe a
        # previously confirmed connection.
        token_changed = bool(token) and token != existing_token
        chat_changed = chat != state["chat_id"]
        if token_changed or chat_changed:
            state.update(connected=False, last_error=None, telegram_verified_at=None)
        state.update(chat_id=chat, auto_enabled=enabled)
    return status(database, settings, clock)


def success(state, clock, kind):
    stamp = now(clock).isoformat()
    state.update(last_successful_backup_at=stamp,
                 last_successful_month=clock.today().strftime("%Y-%m"), last_backup_kind=kind)
    if kind != "download":
        state["last_telegram_backup_at"] = stamp


def record_download(database, clock):
    with locked(database) as state:
        success(state, clock, "download")


def perform(database, settings, clock, *, automatic=False, check_only=False):
    stamp = now(clock)
    claim = uuid.uuid4().hex
    with locked(database) as state:
        if automatic and (not state["auto_enabled"] or not due(state, clock)
                          or not state["chat_id"] or not secret_path(settings).is_file()
                          or (state["next_auto_attempt_at"] and state["next_auto_attempt_at"] > stamp.isoformat())):
            return
        if state["claim_until"] > stamp.timestamp() or (not check_only and state["manual_after"] > stamp.timestamp()):
            if automatic:
                return
            raise TelegramError("Отправка уже выполняется или только что завершилась. Подождите немного.", status_code=409)
        if not state["chat_id"] or not secret_path(settings).is_file():
            raise TelegramError("Сначала сохраните токен бота и идентификатор чата.", status_code=422)
        state.update(claim=claim, claim_until=stamp.timestamp() + 600)
        if not check_only:
            # Persist before I/O: crashes and reloads cannot cause a retry storm.
            state["next_auto_attempt_at"] = (stamp + timedelta(days=1)).isoformat()
        chat = state["chat_id"]
    error = None
    try:
        token = secret(settings)
        if check_only:
            telegram_backup.check(token, chat)
        else:
            raw = backup.make_archive(backup.read_snapshot(database), stamp)
            telegram_backup.send(token, chat, raw, clock.now())
    except TelegramError as exc:
        error = exc
    except Exception:
        # The fallback text must not tell the user a *check* could have sent
        # data — only an actual send can have done that.
        error = TelegramError(
            "Не удалось проверить подключение к Telegram. Проверьте интернет и повторите попытку."
            if check_only else
            "Не удалось создать или отправить резервную копию. Проверьте доступ к данным и повторите попытку.")
    with locked(database) as state:
        if state["claim"] == claim:
            state.update(claim=None, claim_until=0, last_error=error.message if error else None,
                         connected=error is None)
            if error is None:
                state["telegram_verified_at"] = now(clock).isoformat()
            if not check_only:
                state["manual_after"] = now(clock).timestamp() + 30
            if not error and not check_only:
                success(state, clock, "auto-telegram" if automatic else "telegram")
                state["next_auto_attempt_at"] = None
    if error and not automatic:
        raise error from None


def try_automatic(database, settings, clock):
    try:
        perform(database, settings, clock, automatic=True)
    except Exception:
        # Unmigrated/unavailable DB must not break readiness or log secret traces.
        return
