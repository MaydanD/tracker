# Self-contained checks; no Pester, no service launch or dependency installation.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
function Assert($condition, $message) { if (-not $condition) { throw $message } }
foreach ($name in @('start-tracker.ps1', 'dev-backend.ps1', 'dev-frontend.ps1')) {
    $tokens = $null; $errors = $null
    [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $name), [ref]$tokens, [ref]$errors) | Out-Null
    Assert ($errors.Count -eq 0) "Invalid PowerShell syntax: $name"
}
$source = Get-Content (Join-Path $PSScriptRoot 'start-tracker.ps1') -Raw
Assert ($source -match 'WindowStyle Hidden') 'Service windows must be hidden'
Assert ($source -match 'Threading.Mutex') 'Parallel launches must be serialized'
Assert ($source -notmatch 'npm install|pip install') 'Launcher must not install dependencies'
Assert ($source -match 'api/ready' -and $source -match 'api/health') 'Launcher must use readiness and identity checks'
$batch = Get-Content (Join-Path $repoRoot 'start-tracker.bat') -Raw
Assert ($batch.Contains('%~dp0')) 'BAT must resolve its own directory'
Assert ($batch -match 'if errorlevel 1' -and $batch -match 'pause' -and $batch -match 'exit /b 1') 'BAT must preserve failed startup output and exit status'

# Exercise the real functions with service/process doubles.
$ast = [Management.Automation.Language.Parser]::ParseInput($source, [ref]$null, [ref]$null)
foreach ($function in $ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    . ([scriptblock]::Create($function.Extent.Text))
}
$creation = [datetime]'2026-09-28T12:00:00Z'
$ownedFile = Join-Path $repoRoot ('.data/launcher-check-' + [guid]::NewGuid().ToString('N') + '.json')
try {
    @([pscustomobject]@{ pid = 1; started = 'one' }, [pscustomobject]@{ pid = 2; started = 'two' }) | ConvertTo-Json | Set-Content -LiteralPath $ownedFile
    $loaded = @(Read-Owners)
    Assert ($loaded.Count -eq 2 -and $loaded[0].pid -eq 1 -and $loaded[1].pid -eq 2) 'Owners must be emitted as individual records on Windows PowerShell 5.1'
} finally { Remove-Item -LiteralPath $ownedFile -ErrorAction SilentlyContinue }
function Get-Process { param($Id, $ErrorAction) return [pscustomobject]@{ StartTime = $creation } }
Assert (Test-Owned ([pscustomobject]@{ pid = 1; started = $creation.ToUniversalTime().ToString('o') })) 'Owned PID rejected'
Assert (-not (Test-Owned ([pscustomobject]@{ pid = 1; started = $creation.AddSeconds(-1).ToUniversalTime().ToString('o') }))) 'Reused PID must never be stopped'
function Test-Service { param($service) return $true }
function Start-Process { throw 'An already healthy service must not be spawned' }
Start-ServiceProcess 'backend' 8000
Start-ServiceProcess 'frontend' 17373
function Test-Service { param($service) return $false }
function Read-Owners { return @() }
function Test-Port { param($port) return $true }
$rejected = $false
try { Start-ServiceProcess 'backend' 8000 } catch { $rejected = $_.Exception.Message -match '8000' }
Assert $rejected 'An occupied unhealthy port must be rejected'
Write-Host 'Launcher checks passed: syntax, paths, error handling, ownership, reuse, occupied port.'
