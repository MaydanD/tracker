# Creates the backend virtual environment and installs dependencies.
# Usage (from the repository root):  powershell -ExecutionPolicy Bypass -File scripts\setup-backend.ps1

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot 'backend'
$venv = Join-Path $backend '.venv'
$python = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment at $venv"
    python -m venv $venv
}

Write-Host 'Installing backend dependencies'
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $backend 'requirements-dev.txt')

Push-Location $backend
try {
    Write-Host 'Applying database migrations'
    & $python -m alembic upgrade head
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Backend ready. Start it with: powershell -File scripts\dev-backend.ps1'
