param(
    [ValidateSet('Production', 'Development')][string]$Mode = 'Production',
    [ValidateSet('127.0.0.1', '0.0.0.0')][string]$HostAddress = '127.0.0.1',
    [ValidateRange(1024, 65535)][int]$ApiPort = 8000,
    [ValidateRange(1024, 65535)][int]$FrontendPort = 5173,
    [switch]$SkipBuild,
    [switch]$StartLocalMysql
)
$ErrorActionPreference = 'Stop'
$repositoryPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Push-Location -LiteralPath $repositoryPath
$frontendProcess = $null
$previousProxyTarget = $env:CELLLENS_API_PROXY_TARGET
try {
    foreach ($program in @('uv', 'node', 'npm.cmd')) {
        if (-not (Get-Command $program -ErrorAction SilentlyContinue)) { throw "$program is required" }
    }
    if ($StartLocalMysql) { & (Join-Path $PSScriptRoot 'start_mysql.ps1') }
    & uv run --no-sync python scripts/check_mysql.py
    if ($LASTEXITCODE -ne 0) { throw 'Database unavailable. Configure .env and start MySQL before launching.' }
    & uv run --no-sync alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
    if (-not (Test-Path -LiteralPath 'frontend/node_modules/.package-lock.json')) {
        & npm.cmd --prefix frontend ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    }
    if ($Mode -eq 'Production') {
        if (-not $SkipBuild) {
            & npm.cmd --prefix frontend run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
        }
        if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Build is missing; remove -SkipBuild' }
        Write-Host "CellLens: http://127.0.0.1:$ApiPort/workbench"
    } else {
        if ($ApiPort -eq $FrontendPort) { throw 'Development ports must be different' }
        $env:CELLLENS_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
        $vitePath = Join-Path $repositoryPath 'frontend/node_modules/vite/bin/vite.js'
        $nodePath = (Get-Command node).Source
        $frontendArguments = @(('"{0}"' -f $vitePath), '--host', $HostAddress, '--port', $FrontendPort, '--strictPort')
        $frontendProcess = Start-Process -FilePath $nodePath -ArgumentList $frontendArguments -WorkingDirectory (Join-Path $repositoryPath 'frontend') -WindowStyle Hidden -PassThru
        Write-Host "CellLens development: http://127.0.0.1:$FrontendPort/workbench"
    }
    & uv run --no-sync uvicorn backend.app.main:app --host $HostAddress --port $ApiPort
    if ($LASTEXITCODE -ne 0) { throw 'API stopped with an error' }
} finally {
    if ($frontendProcess -and -not $frontendProcess.HasExited) { Stop-Process -Id $frontendProcess.Id }
    $env:CELLLENS_API_PROXY_TARGET = $previousProxyTarget
    Pop-Location
}
