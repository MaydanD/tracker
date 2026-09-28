# Uses the existing service scripts. No dependency installation at launch.
param([switch]$Stop, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $repoRoot '.data\launcher'
$frontendUrl = 'http://127.0.0.1:17373'
$backendUrl = 'http://127.0.0.1:8000'
$ownedFile = Join-Path $runtime 'processes.json'
$hash = [System.Security.Cryptography.SHA256]::Create()
$key = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($repoRoot.ToLowerInvariant()))).Replace('-', '')
$hash.Dispose()
$mutex = New-Object Threading.Mutex($false, "Local\TrackerLauncher-$key")
$acquired = $false

function Read-Owners {
    if (Test-Path -LiteralPath $ownedFile) {
        $records = Get-Content -LiteralPath $ownedFile -Raw | ConvertFrom-Json
        foreach ($record in $records) { Write-Output $record }
    }
}
function Test-Owned($record) {
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    return $process -and $process.StartTime.ToUniversalTime().ToString('o') -eq $record.started
}
function Test-Service([string]$service) {
    try {
        if ($service -eq 'backend') {
            $health = Invoke-RestMethod "$backendUrl/api/health" -TimeoutSec 2
            $ready = Invoke-RestMethod "$backendUrl/api/ready" -TimeoutSec 2
            return $health.app -eq 'Tracker' -and $ready.status -eq 'ready'
        }
        $page = Invoke-WebRequest $frontendUrl -UseBasicParsing -TimeoutSec 2
        $health = Invoke-RestMethod "$frontendUrl/api/health" -TimeoutSec 2
        return $page.Content -match '/src/main.tsx' -and $health.app -eq 'Tracker'
    } catch { return $false }
}
function Test-Port([int]$port) {
    $socket = New-Object Net.Sockets.TcpClient
    try { $socket.Connect('127.0.0.1', $port); return $true } catch { return $false } finally { $socket.Dispose() }
}
function Wait-Service([string]$service, $record) {
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        if (Test-Service $service) { return }
        if ($record -and -not (Test-Owned $record)) { break }
        Start-Sleep -Milliseconds 500
    }
    throw "Сервис $service не запустился. Журналы: $runtime\$service.err.log и $runtime\$service.out.log"
}
function Start-ServiceProcess([string]$service, [int]$port) {
    if (Test-Service $service) { Write-Host "Сервис $service уже работает."; return }
    $records = @(Read-Owners)
    $previous = $records | Where-Object { $_.service -eq $service -and (Test-Owned $_) } | Select-Object -First 1
    if ($previous) { Wait-Service $service $previous; return }
    if (Test-Port $port) { throw "Порт $port занят, но сервис $service не готов. Освободите порт или проверьте настройки Tracker." }
    if ($service -eq 'backend' -and -not (Test-Path (Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'))) {
        throw 'Среда не подготовлена. Сначала выполните powershell -File scripts\setup-backend.ps1'
    }
    if ($service -eq 'frontend') {
        if (-not (Test-Path (Join-Path $repoRoot 'frontend\node_modules'))) { throw 'Среда не подготовлена. Сначала выполните в папке frontend: npm ci' }
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Не найден npm. Установите Node.js и подготовьте frontend: npm ci' }
    }
    $script = Join-Path $PSScriptRoot "dev-$service.ps1"
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
    if ($service -eq 'backend') { $arguments += ' -NoReload' }
    $process = Start-Process powershell.exe -ArgumentList $arguments -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime "$service.out.log") -RedirectStandardError (Join-Path $runtime "$service.err.log")
    $record = [pscustomobject]@{ service = $service; pid = $process.Id; started = $process.StartTime.ToUniversalTime().ToString('o') }
    @($records | Where-Object { $_.service -ne $service }) + @($record) | ConvertTo-Json | Set-Content -LiteralPath $ownedFile -Encoding UTF8
    Wait-Service $service $record
}
function Stop-OwnedProcesses {
    foreach ($record in @(Read-Owners)) {
        if (-not (Test-Owned $record)) { continue }
        # Snapshot the tree while its proven owner exists; never match by image name.
        $all = @(Get-CimInstance Win32_Process)
        $ids = @([int]$record.pid)
        do {
            $children = @($all | Where-Object { $_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids })
            $ids += @($children | ForEach-Object { [int]$_.ProcessId })
        } while ($children.Count -gt 0)
        [array]::Reverse($ids)
        foreach ($processId in $ids) {
            $snapshot = $all | Where-Object ProcessId -eq $processId | Select-Object -First 1
            $live = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
            if ($snapshot -and $live -and $snapshot.CreationDate -eq $live.CreationDate) { Stop-Process -Id $processId -ErrorAction SilentlyContinue }
        }
        Write-Host "Сервис $($record.service) остановлен."
    }
    if (Test-Path -LiteralPath $ownedFile) { Remove-Item -LiteralPath $ownedFile }
}
try {
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    try { $acquired = $mutex.WaitOne(120000) } catch [Threading.AbandonedMutexException] { $acquired = $true }
    if (-not $acquired) { throw 'Другой запуск Tracker ещё выполняется. Повторите позже.' }
    if ($Stop) { Stop-OwnedProcesses; exit 0 }
    Write-Host 'Запускаем Tracker…'
    Start-ServiceProcess 'backend' 8000
    Start-ServiceProcess 'frontend' 17373
    if (-not $NoBrowser) { Start-Process $frontendUrl }
    Write-Host "Tracker готов: $frontendUrl"
} catch {
    Write-Host "Не удалось выполнить запуск или остановку Tracker: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($acquired) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
