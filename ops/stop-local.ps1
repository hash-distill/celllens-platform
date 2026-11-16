[CmdletBinding(SupportsShouldProcess)]
param()
$ErrorActionPreference = 'Stop'
$projectDirectory = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$processFile = Join-Path $projectDirectory 'data\runtime\processes.json'
$pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\python.exe'
. (Join-Path $PSScriptRoot 'local-processes.ps1')
if (-not (Test-Path -LiteralPath $processFile -PathType Leaf)) {
    Write-Output 'No recorded local CellLens services.'
    return
}
$saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
if ($saved.schema_version -ne 1 -or $saved.workspace -ne $projectDirectory) {
    throw 'Process record does not identify this workspace; no process was stopped.'
}
# Validate all live roots before stopping any, including creation time to prevent PID reuse.
$services = @(@{role='api'; module='uvicorn'}, @{role='worker'; module='backend.app.worker'}, @{role='gpu'; module='backend.app.worker'})
foreach ($entry in $services) {
    $identity = $saved.($entry.role)
    if ($identity -and (Get-CellLensIdentity -ProcessId $identity.pid) -and
        -not (Test-CellLensIdentity -Expected $identity -PythonExecutable $pythonExecutable -Module $entry.module)) {
        throw "Recorded $($entry.role) PID no longer matches this workspace; no process was stopped."
    }
}
foreach ($entry in $services) {
    $identity = $saved.($entry.role)
    if ($identity) { Stop-CellLensProcessTree -Expected $identity -PythonExecutable $pythonExecutable -Module $entry.module -WhatIf:$WhatIfPreference -Confirm:$false }
}
if (-not $WhatIfPreference) {
    Remove-Item -LiteralPath $processFile
    Write-Output 'Stopped the recorded CellLens workspace services. Database, results and logs were preserved.'
}
