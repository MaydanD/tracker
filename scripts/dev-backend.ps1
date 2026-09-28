# Migrates the database and starts the FastAPI development server.
# Usage (from the repository root):  powershell -File scripts\dev-backend.ps1

param([switch]$NoReload)
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw "Среда не подготовлена: $backend\.venv. Сначала выполните scripts\setup-backend.ps1."
}

Push-Location $backend
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось обновить базу данных. Запуск отменён.' }
    if ($NoReload) { & $python -m app } else { & $python -m app --reload }
    if ($LASTEXITCODE -ne 0) { throw 'Сервер Tracker завершился с ошибкой.' }
}
finally {
    Pop-Location
}
