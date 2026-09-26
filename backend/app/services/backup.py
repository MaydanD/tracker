"""Versioned logical backups, read-only exports, and atomic full replacement."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import struct
import time
import uuid
import zipfile
import zlib
from datetime import date, datetime

from pydantic import ValidationError
from sqlalchemy import select, text

from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.migrations import expected_revision
from app.db.models import Area, Habit, HabitVersion, DailyHabitEntry, DailyState, Experiment, InsightSnapshot
from app.domain.backup import BackupError, require, validate_relations
from app.schemas.backup import BackupDataV1, ManifestV1

logger = get_logger(__name__)
FORMAT_VERSION = 1
V1_REVISION = "c3f1a7b24d90"
TOKEN_TTL = 1800
# Explicit allowlist: infrastructure tables and future secret-bearing tables
# cannot accidentally join a backup. Columns are pinned by the v1 DTO below.
TABLES = {
    "areas": Area.__table__, "habits": Habit.__table__,
    "habit_versions": HabitVersion.__table__, "habit_entries": DailyHabitEntry.__table__,
    "daily_states": DailyState.__table__, "experiments": Experiment.__table__,
    "insight_snapshots": InsightSnapshot.__table__,
}


def json_bytes(value) -> bytes:
    def encode(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError(type(item).__name__)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, default=encode).encode("utf-8")


def snapshot(session) -> dict:
    """Seven ordered Core selects: no ORM eager loads and no N+1."""
    result = {}
    for name, table in TABLES.items():
        row_type = BackupDataV1.model_fields[name].annotation.__args__[0]
        columns = [table.c[field] for field in row_type.model_fields]
        result[name] = [dict(row) for row in session.execute(
            select(*columns).order_by(table.c.id)).mappings()]
    return result


def read_snapshot(database) -> dict:
    with database.session() as session:
        # sqlite3 legacy transaction mode does not BEGIN for SELECT. Explicitly
        # establish one snapshot spanning all seven queries.
        session.execute(text("BEGIN"))
        return snapshot(session)


def make_archive(data: dict, moment: datetime) -> bytes:
    manifest = {
        "format": "tracker-backup", "version": FORMAT_VERSION,
        "created_at": moment.isoformat(), "alembic_revision": expected_revision(),
        "application_backup_version": FORMAT_VERSION,
        "counts": {name: len(rows) for name, rows in data.items()},
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json_bytes(manifest))
        archive.writestr("data.json", json_bytes(data))
    return output.getvalue()


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON содержит повторяющиеся ключи.")
        result[key] = value
    return result


def _json(raw):
    def bad_constant(_):
        raise BackupError("JSON содержит недопустимое число.")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=bad_constant)


def normalize_v1(manifest: dict, data_raw: bytes):
    """v1 → current DTO. Future versions get their own normalizer here."""
    require(manifest.get("alembic_revision") == V1_REVISION, "Неподдерживаемая схема резервной копии.")
    require(type(manifest.get("application_backup_version")) is int,
            "Некорректная версия приложения резервного копирования.")
    parsed_manifest = ManifestV1.model_validate_json(json_bytes(manifest))
    _json(data_raw)  # Reject duplicate keys and nonstandard numeric constants.
    data = BackupDataV1.model_validate_json(data_raw)
    require(parsed_manifest.counts == {name: len(getattr(data, name)) for name in TABLES},
            "Количество записей не совпадает с манифестом.")
    validate_relations(data)
    return parsed_manifest, data


NORMALIZERS = {1: normalize_v1}


def validate_archive(raw: bytes, settings):
    require(len(raw) <= settings.backup_max_upload_bytes, "Файл превышает допустимый размер.")
    try:
        # Reject excessive entry count *before* ZipFile allocates ZipInfo objects.
        # ZIP64 is unnecessary with our limits and is intentionally unsupported.
        eocd = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557))
        require(eocd >= 0 and len(raw) >= eocd + 22, "Файл не является корректным ZIP-архивом.")
        disk, cd_disk, disk_entries, entries = struct.unpack_from("<4H", raw, eocd + 4)
        require(disk == cd_disk == 0 and disk_entries == entries == 2,
                "ZIP должен содержать ровно manifest.json и data.json.")
        cd_size, cd_offset = struct.unpack_from("<2I", raw, eocd + 12)
        require(cd_offset + cd_size == eocd, "Некорректный каталог ZIP; ZIP64 не поддерживается.")
        position = cd_offset
        for _ in range(2):
            require(position + 46 <= eocd and raw[position:position + 4] == b"PK\x01\x02",
                    "Повреждён каталог ZIP.")
            name_len, extra_len, comment_len = struct.unpack_from("<3H", raw, position + 28)
            position += 46 + name_len + extra_len + comment_len
        require(position == eocd, "ZIP содержит неожиданные файлы или повреждённый каталог.")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            require(len(infos) == 2 and {item.filename for item in infos} == {"manifest.json", "data.json"},
                    "ZIP должен содержать ровно manifest.json и data.json; пути и повторы запрещены.")
            require(sum(item.file_size for item in infos) <= settings.backup_max_uncompressed_bytes,
                    "Распакованные данные превышают допустимый размер.")
            contents = {}
            remaining = settings.backup_max_uncompressed_bytes
            for item in infos:
                require(not item.flag_bits & 1 and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        "Зашифрованный или неподдерживаемый ZIP.")
                require(item.external_attr >> 16 & 0o170000 != 0o120000, "Ссылки внутри ZIP запрещены.")
                # Never extract to disk. Bounded decompression also verifies CRC.
                with archive.open(item) as member:
                    contents[item.filename] = member.read(remaining + 1)
                remaining -= len(contents[item.filename])
                require(remaining >= 0, "Распакованные данные превышают допустимый размер.")
        manifest = _json(contents["manifest.json"])
        require(isinstance(manifest, dict), "Некорректный манифест.")
        require(manifest.get("format") == "tracker-backup", "Это не резервная копия Tracker.")
        version = manifest.get("version")
        require(type(version) is int, "Некорректная версия резервной копии.")
        require(version <= FORMAT_VERSION, "Резервная копия создана более новой версией Tracker.")
        require(version in NORMALIZERS, "Неподдерживаемая версия резервной копии.")
        return NORMALIZERS[version](manifest, contents["data.json"])
    except BackupError:
        raise
    except ValidationError as exc:
        error = exc.errors(include_input=False)[0]
        location = ".".join(str(part) for part in error["loc"])
        reason = {
            "missing": "отсутствует обязательное поле", "extra_forbidden": "неизвестное поле",
            "literal_error": "недопустимое значение", "int_type": "требуется целое число",
            "bool_type": "требуется true или false", "string_type": "требуется текст",
            "list_type": "требуется список", "greater_than_equal": "значение меньше допустимого",
            "less_than_equal": "значение больше допустимого", "value_error": "нарушен формат или правило поля",
        }.get(error["type"], "недопустимый тип, формат или диапазон значения")
        raise BackupError(f"Некорректное поле {location}: {reason}.") from exc
    except AppError as exc:
        raise BackupError(f"Нарушены правила данных: {exc.code}.") from exc
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError, zipfile.BadZipFile,
            NotImplementedError, RuntimeError, EOFError, zlib.error) as exc:
        raise BackupError("Повреждённый ZIP или некорректный JSON в резервной копии.") from exc


def validation_token(raw: bytes, key: bytes, *, issued: int | None = None) -> str:
    issued = int(time.time()) if issued is None else issued
    message = f"{issued}:{hashlib.sha256(raw).hexdigest()}"
    return f"{issued}.{hmac.new(key, message.encode(), hashlib.sha256).hexdigest()}"


def check_token(raw: bytes, token: str, key: bytes) -> None:
    try:
        issued = int(token.split(".")[0])
        valid = 0 <= time.time() - issued <= TOKEN_TTL and hmac.compare_digest(
            token, validation_token(raw, key, issued=issued))
    except (ValueError, OverflowError, TypeError):
        valid = False
    require(valid, "Сначала проверьте этот файл заново: подтверждение отсутствует или устарело.")


def _write_safety(raw: bytes, settings, moment: datetime) -> str:
    directory = settings.resolved_backups_dir
    directory.mkdir(parents=True, exist_ok=True)
    name = f"tracker-before-restore-{moment.strftime('%Y-%m-%dT%H%M%S')}-{uuid.uuid4().hex}.zip"
    target = directory / name
    temporary = target.with_suffix(".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return name


def restore(database, data: BackupDataV1, settings, moment: datetime) -> str:
    """Lock → durable safety snapshot → FK-safe delete/insert → single commit.

    No FK disabling; a failed insert/commit rolls back all seven tables. Safety
    archives are retained on both success and failure, outside the transaction.
    """
    try:
        with database.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            safety = _write_safety(make_archive(snapshot(session), moment), settings, moment)
            for table in reversed(list(TABLES.values())):
                session.execute(table.delete())
            for section, table in TABLES.items():
                rows = getattr(data, section)
                for offset in range(0, len(rows), 1000):
                    session.execute(table.insert(), [row.model_dump() for row in rows[offset:offset + 1000]])
            session.commit()
            return safety
    except Exception as exc:
        logger.exception("Logical restore rolled back")
        raise BackupError("Восстановление не выполнено. Текущие данные сохранены. Проверьте доступ к базе и папке резервных копий.",
                          code="restore_failed", status_code=500) from exc


def csv_archive(data: dict) -> bytes:
    output = io.BytesIO()
    def cell(value):
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        # Spreadsheet programs must not evaluate user-authored titles/notes.
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
        return value
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, rows in data.items():
            row_type = BackupDataV1.model_fields[name].annotation.__args__[0]
            fields = list(row_type.model_fields)
            stream = io.StringIO(newline="")
            writer = csv.writer(stream)
            writer.writerow(fields)
            writer.writerows([cell(row[field]) for field in fields] for row in rows)
            archive.writestr(f"{name}.csv", stream.getvalue().encode("utf-8-sig"))
    return output.getvalue()
