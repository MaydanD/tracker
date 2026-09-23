# Installs (if needed) and starts the Vite development server.
# Usage (from the repository root):  powershell -File scripts\dev-frontend.ps1

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $repoRoot 'frontend'

Push-Location $frontend
try {
    if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
        Write-Host 'Installing frontend dependencies'
        npm install
    }

    npm run dev
}
finally {
    Pop-Location
}
