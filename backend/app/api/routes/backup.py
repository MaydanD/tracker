"""Binary uploads avoid multipart spooling before size enforcement."""
from datetime import UTC

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import ClockDep, DatabaseDep, SettingsDep
from app.domain.backup import BackupError
from app.schemas.backup import BackupPreview
from app.services import backup

router = APIRouter(tags=["data"])
ZIP_BODY = {"requestBody": {"required": True, "content": {
    "application/zip": {"schema": {"type": "string", "format": "binary"}},
}}}
ZIP_RESPONSE = {200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}}}


def download(raw: bytes, filename: str, media_type: str):
    return Response(raw, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@router.get("/backup", response_class=Response, responses=ZIP_RESPONSE)
def get_backup(database: DatabaseDep, clock: ClockDep):
    moment = clock.now().astimezone(UTC)
    raw = backup.make_archive(backup.read_snapshot(database), moment)
    return download(raw, f"tracker-backup-{moment.strftime('%Y-%m-%dT%H%M%S')}.zip", "application/zip")


@router.get("/export/json", response_class=Response, responses={200: {"content": {"application/json": {}}}})
def export_json(database: DatabaseDep, clock: ClockDep):
    return download(backup.json_bytes({"data": backup.read_snapshot(database)}),
                    f"tracker-export-{clock.today().isoformat()}.json", "application/json")


@router.get("/export/csv", response_class=Response, responses=ZIP_RESPONSE)
def export_csv(database: DatabaseDep, clock: ClockDep):
    return download(backup.csv_archive(backup.read_snapshot(database)),
                    f"tracker-export-{clock.today().isoformat()}.zip", "application/zip")


async def upload(request, settings) -> bytes:
    limit = settings.backup_max_upload_bytes
    length = request.headers.get("content-length")
    if length is not None:
        try:
            too_large = int(length) > limit
        except ValueError:
            raise BackupError("Некорректный размер файла.")
        if too_large:
            raise BackupError("Файл превышает допустимый размер.", status_code=413)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise BackupError("Файл превышает допустимый размер.", status_code=413)
        body.extend(chunk)
    return bytes(body)


@router.post("/backup/validate", response_model=BackupPreview, openapi_extra=ZIP_BODY)
async def validate(request: Request, settings: SettingsDep, response: Response):
    raw = await upload(request, settings)
    manifest, _ = await run_in_threadpool(backup.validate_archive, raw, settings)
    response.headers["Cache-Control"] = "no-store"
    return BackupPreview(manifest=manifest,
                         validation_token=backup.validation_token(raw, request.app.state.backup_signing_key),
                         expires_in_seconds=backup.TOKEN_TTL)


@router.post("/backup/restore", openapi_extra={**ZIP_BODY, "parameters": [
    {"name": "X-Tracker-Confirm-Restore", "in": "header", "required": True,
     "schema": {"type": "string", "enum": ["replace"]}},
    {"name": "X-Tracker-Validation-Token", "in": "header", "required": True,
     "schema": {"type": "string"}},
]})
async def restore(request: Request, settings: SettingsDep, database: DatabaseDep, clock: ClockDep):
    if request.headers.get("x-tracker-confirm-restore") != "replace":
        raise BackupError("Подтвердите замену текущих данных.")
    raw = await upload(request, settings)
    backup.check_token(raw, request.headers.get("x-tracker-validation-token", ""), request.app.state.backup_signing_key)
    _, data = await run_in_threadpool(backup.validate_archive, raw, settings)
    safety = await run_in_threadpool(backup.restore, database, data, settings, clock.now().astimezone(UTC))
    return {"status": "restored", "counts": {name: len(getattr(data, name)) for name in backup.TABLES},
            "safety_backup": safety}
