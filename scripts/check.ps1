# Runs every Stage 1 quality gate: backend tests, frontend tests, typecheck and build.
# Usage (from the repository root):  powershell -File scripts\check.ps1

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot 'backend'
$frontend = Join-Path $repoRoot 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw "Virtual environment not found at $backend\.venv. Run scripts\setup-backend.ps1 first."
}

Write-Host '== Backend: pytest ==' -ForegroundColor Cyan
Push-Location $backend
try {
    & $python -m pytest
}
finally {
    Pop-Location
}

Write-Host '== Backend: migrations on a temporary database ==' -ForegroundColor Cyan
$tempData = Join-Path ([System.IO.Path]::GetTempPath()) ("tracker-check-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempData -Force | Out-Null
try {
    Push-Location $backend
    try {
        $env:TRACKER_DATA_DIR = $tempData
        & $python -m alembic upgrade head
        & $python -m alembic current
    }
    finally {
        Remove-Item Env:\TRACKER_DATA_DIR -ErrorAction SilentlyContinue
        Pop-Location
    }
}
finally {
    Remove-Item -Recurse -Force $tempData -ErrorAction SilentlyContinue
}

Write-Host '== Frontend: tests, typecheck, build ==' -ForegroundColor Cyan
Push-Location $frontend
try {
    npm test
    npm run typecheck
    npm run build
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'All Stage 1 checks passed.' -ForegroundColor Green
