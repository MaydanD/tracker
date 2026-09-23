# Runs every quality gate: backend tests, migrations on a fresh database, frontend tests,
# typecheck and build.
# Usage (from the repository root):  powershell -File scripts\check.ps1

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot 'backend'
$frontend = Join-Path $repoRoot 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source

function Assert-ExitCode([string]$step) {
    if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE)." }
}

if (-not (Test-Path $python)) {
    throw "Virtual environment not found at $backend\.venv. Run scripts\setup-backend.ps1 first."
}

Write-Host '== Backend: pytest ==' -ForegroundColor Cyan
Push-Location $backend
try {
    & $python -m pytest
    Assert-ExitCode 'pytest'
}
finally {
    Pop-Location
}

Write-Host '== Backend: migrations on a temporary database ==' -ForegroundColor Cyan
$tempData = Join-Path ([System.IO.Path]::GetTempPath()) ("tracker-check-" + [Guid]::NewGuid().ToString('N'))
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$tempData = [System.IO.Path]::GetFullPath($tempData)
if (-not $tempData.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Temporary check directory is outside the temporary root.'
}
$previousDataDir = $env:TRACKER_DATA_DIR
$previousDatabaseUrl = $env:TRACKER_DATABASE_URL
New-Item -ItemType Directory -Path $tempData -Force | Out-Null
try {
    Push-Location $backend
    try {
        $env:TRACKER_DATA_DIR = $tempData
        $env:TRACKER_DATABASE_URL = 'sqlite:///' + (Join-Path $tempData 'check.sqlite3').Replace('\', '/')
        & $python -m alembic upgrade head
        Assert-ExitCode 'alembic upgrade head'
        & $python -m alembic current
        Assert-ExitCode 'alembic current'
        & $python -m alembic check
        Assert-ExitCode 'alembic check'
    }
    finally {
        $env:TRACKER_DATA_DIR = $previousDataDir
        $env:TRACKER_DATABASE_URL = $previousDatabaseUrl
        Pop-Location
    }
}
finally {
    Remove-Item -LiteralPath $tempData -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host '== Frontend: tests, typecheck, build ==' -ForegroundColor Cyan
Push-Location $frontend
try {
    & $npm test
    Assert-ExitCode 'npm test'
    & $npm run typecheck
    Assert-ExitCode 'npm run typecheck'
    & $npm run build
    Assert-ExitCode 'npm run build'
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'All checks passed.' -ForegroundColor Green
