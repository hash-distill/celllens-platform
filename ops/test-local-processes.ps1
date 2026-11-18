# Pure identity regression: Get-CellLensIdentity is mocked; no real service is queried or stopped.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-processes.ps1')
$pythonExecutable = 'C:\test\celllens\.venv\Scripts\python.exe'
$testCommand = '"' + $pythonExecutable + '" -m backend.app.worker --kind cpu'
$stamp = '2026-11-07T05:00:00.1234567Z'
$script:mockIdentity = [pscustomobject]@{pid=12345; parent_pid=1; created_at=$stamp; command_line=$testCommand}
function Get-CellLensIdentity {
    param([int]$ProcessId)
    return $script:mockIdentity
}
$script:checks = 0
function Assert-Identity {
    param([string]$Label, $Expected, [bool]$Accepted)
    $actual = Test-CellLensIdentity -Expected $Expected -PythonExecutable $pythonExecutable -Module 'backend.app.worker'
    if ([bool]$actual -ne $Accepted) { throw "Identity regression failed: $Label" }
    $script:checks++
}
function New-TestIdentity {
    param($Created = $stamp, [int]$ProcessId = 12345, [string]$Command = $testCommand)
    return [pscustomobject]@{pid=$ProcessId; created_at=$Created; command_line=$Command}
}
$roundtrip = New-TestIdentity | ConvertTo-Json | ConvertFrom-Json
Assert-Identity 'JSON roundtrip' $roundtrip $true
Assert-Identity 'Windows PowerShell 5 string timestamp' (New-TestIdentity -Created $stamp) $true
$typedUtc = [DateTime]::Parse($stamp, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
Assert-Identity 'DateTime UTC timestamp' (New-TestIdentity -Created $typedUtc) $true
$offsetTime = [DateTimeOffset]::Parse('2026-11-07T13:00:00.1234567+08:00', [Globalization.CultureInfo]::InvariantCulture)
Assert-Identity 'DateTimeOffset same instant' (New-TestIdentity -Created $offsetTime) $true
Assert-Identity 'Different creation tick' (New-TestIdentity -Created $offsetTime.AddTicks(1)) $false
Assert-Identity 'Different command' (New-TestIdentity -Command ($testCommand + ' --once')) $false
Assert-Identity 'Different PID' (New-TestIdentity -ProcessId 12346) $false
Assert-Identity 'Invalid timestamp' (New-TestIdentity -Created 'not-a-time') $false
Write-Output "CellLens process identity: $($script:checks) mock regressions passed."
