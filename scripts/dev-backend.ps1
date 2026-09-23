# Migrates the database and starts the FastAPI development server.
# Usage (from the repository root):  powershell -File scripts\dev-backend.ps1

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw "Virtual environment not found at $backend\.venv. Run scripts\setup-backend.ps1 first."
}

Push-Location $backend
try {
    & $python -m alembic upgrade head
    & $python -m app --reload
}
finally {
    Pop-Location
}
