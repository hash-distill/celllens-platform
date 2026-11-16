param(
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [ValidateRange(10, 300)][int]$StartupTimeoutSeconds = 90,
    [switch]$Install,
    [switch]$Gpu
)
$ErrorActionPreference = 'Stop'
$projectDirectory = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$runtimeDirectory = Join-Path $projectDirectory 'data\runtime'
$processFile = Join-Path $runtimeDirectory 'processes.json'
$pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\python.exe'
. (Join-Path $PSScriptRoot 'local-processes.ps1')
Set-Location -LiteralPath $projectDirectory
if (Test-Path -LiteralPath $processFile) {
    $saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    if ($saved.workspace -ne $projectDirectory) { throw 'Existing process record belongs to another workspace' }
    foreach ($role in @('api', 'worker', 'gpu')) {
        if ($saved.$role -and (Get-CellLensIdentity -ProcessId $saved.$role.pid)) {
            throw "Recorded $role process is still present. Run ops/stop-local.ps1 before restarting."
        }
    }
}
# Test the socket before migrations, environment installation or process startup.
$portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
$portProbe.ExclusiveAddressUse = $true
try { $portProbe.Start() }
catch { throw "Port $Port is already in use or unavailable; no services were started." }
finally { $portProbe.Stop() }
if ($Install) {
    $virtualEnvironment = Get-Item -LiteralPath (Join-Path $projectDirectory '.venv') -ErrorAction SilentlyContinue
    if ($virtualEnvironment -and ($virtualEnvironment.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The .venv directory is a shared link. Refusing to modify another workspace environment; use the installed environment without -Install or create a dedicated environment.'
    }
    if ($Gpu) {
        uv sync --frozen --no-dev --extra analysis --extra report --extra model
    } else {
        uv sync --frozen --no-dev --extra analysis --extra report
    }
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    npm --prefix frontend ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
}
if (-not (Test-Path -LiteralPath (Join-Path $projectDirectory 'frontend\dist\index.html') -PathType Leaf)) {
    throw 'Frontend build missing. Run with -Install or build frontend before starting services.'
}
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) { throw 'Install dependencies first with -Install' }
$environmentScripts = Split-Path -Parent $pythonExecutable
if ($environmentScripts -notin $env:PATH.Split([IO.Path]::PathSeparator)) {
    $env:PATH = $environmentScripts + [IO.Path]::PathSeparator + $env:PATH
}
New-Item -ItemType Directory -Force -Path $runtimeDirectory | Out-Null
$databasePath = (Join-Path $runtimeDirectory 'celllens.db').Replace('\', '/')
$env:CELLLENS_PROJECT_ROOT = $projectDirectory
$env:CELLLENS_DATABASE_URL = "sqlite+pysqlite:///$databasePath"
$env:CELLLENS_API_PREFIX = '/api/v1'
$env:CELLLENS_CREATE_DATABASE_SCHEMA = 'false'
$env:CELLLENS_DEPLOYMENT_MODE = 'local'
$env:CELLLENS_WORKER_MODE = 'external'
$predictionFlag = if ($Gpu) { 'true' } else { 'false' }
$env:CELLLENS_WORKER_ENABLED = $predictionFlag
$env:CELLLENS_GPU_AVAILABLE = $predictionFlag
& $pythonExecutable -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed; services were not started' }
$workerIdentity = $null
$apiIdentity = $null
$gpuIdentity = $null
$started = $false
$ready = $false
try {
    $workerProcess = Start-Process -FilePath $pythonExecutable -ArgumentList @('-m', 'backend.app.worker', '--kind', 'cpu') -WorkingDirectory $projectDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDirectory 'worker.log') -RedirectStandardError (Join-Path $runtimeDirectory 'worker.err')
    $workerIdentity = Get-CellLensIdentity -ProcessId $workerProcess.Id
    if ($Gpu) {
        $gpuProcess = Start-Process -FilePath $pythonExecutable -ArgumentList @('-m', 'backend.app.worker', '--kind', 'gpu') -WorkingDirectory $projectDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDirectory 'gpu-worker.log') -RedirectStandardError (Join-Path $runtimeDirectory 'gpu-worker.err')
        $gpuIdentity = Get-CellLensIdentity -ProcessId $gpuProcess.Id
    }
    $apiProcess = Start-Process -FilePath $pythonExecutable -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', "$Port", '--no-proxy-headers') -WorkingDirectory $projectDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDirectory 'api.log') -RedirectStandardError (Join-Path $runtimeDirectory 'api.err')
    $apiIdentity = Get-CellLensIdentity -ProcessId $apiProcess.Id
    $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    do {
        if (-not (Test-CellLensIdentity -Expected $workerIdentity -PythonExecutable $pythonExecutable -Module 'backend.app.worker')) { throw 'CPU worker exited before startup. See data/runtime/worker.err.' }
        if (-not (Test-CellLensIdentity -Expected $apiIdentity -PythonExecutable $pythonExecutable -Module 'uvicorn')) { throw 'API exited before startup. See data/runtime/api.err.' }
        if ($Gpu -and -not (Test-CellLensIdentity -Expected $gpuIdentity -PythonExecutable $pythonExecutable -Module 'backend.app.worker')) { throw 'GPU worker exited before startup. See data/runtime/gpu-worker.err.' }
        $reply = $null
        try { $reply = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/ready" -TimeoutSec 2 }
        catch { } # API may still be importing its dependencies.
        if ($reply -and $reply.ready -and $reply.capabilities.cpu_analysis -and (-not $Gpu -or $reply.capabilities.prediction)) {
            $apiPids = @(Get-CellLensProcessTree -ProcessId $apiIdentity.pid).pid
            $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
            if ($listener -and @($listener | Where-Object { $_.OwningProcess -in $apiPids }).Count -gt 0) {
                $ready = $true
                break
            }
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $ready) { throw 'API/requested workers did not become ready before the startup timeout. See data/runtime logs.' }
    @{schema_version = 1; workspace = $projectDirectory; port = $Port; gpu_enabled = [bool]$Gpu; api = $apiIdentity; worker = $workerIdentity; gpu = $gpuIdentity} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $processFile
    $started = $true
    $gpuDescription = if ($Gpu) { "; GPU worker PID $($gpuIdentity.pid)" } else { '' }
    Write-Output "CellLens ready: http://127.0.0.1:$Port; API PID $($apiIdentity.pid); CPU worker PID $($workerIdentity.pid)$gpuDescription. Stop with ops/stop-local.ps1."
} finally {
    if (-not $started) {
        if ($apiIdentity) { Stop-CellLensProcessTree -Expected $apiIdentity -PythonExecutable $pythonExecutable -Module 'uvicorn' -Confirm:$false }
        if ($workerIdentity) { Stop-CellLensProcessTree -Expected $workerIdentity -PythonExecutable $pythonExecutable -Module 'backend.app.worker' -Confirm:$false }
        if ($gpuIdentity) { Stop-CellLensProcessTree -Expected $gpuIdentity -PythonExecutable $pythonExecutable -Module 'backend.app.worker' -Confirm:$false }
    }
}
