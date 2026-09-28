# Starts the Vite development server after the one-time setup.
# Usage (from the repository root):  powershell -File scripts\dev-frontend.ps1

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $repoRoot 'frontend'

Push-Location $frontend
try {
    if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
        throw 'Среда не подготовлена. Сначала выполните npm ci в папке frontend.'
    }

    npm.cmd run dev -- --host 127.0.0.1
    if ($LASTEXITCODE -ne 0) { throw 'Интерфейс Tracker завершился с ошибкой.' }
}
finally {
    Pop-Location
}
