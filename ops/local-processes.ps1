# Shared process identity checks; no process is stopped merely because a PID matches.
function Get-CellLensIdentity {
    param([int]$ProcessId)
    $value = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if (-not $value) { return $null }
    return [pscustomobject]@{
        pid = [int]$value.ProcessId
        parent_pid = [int]$value.ParentProcessId
        created_at = $value.CreationDate.ToUniversalTime().ToString('o')
        command_line = [string]$value.CommandLine
    }
}

function ConvertTo-CellLensUtcTicks {
    param($Value)
    if ($Value -is [DateTimeOffset]) { return $Value.UtcDateTime.Ticks }
    if ($Value -is [DateTime]) {
        # Records are written in UTC. PowerShell versions may deserialize them
        # as a string or a DateTime; an unspecified typed value retains UTC semantics.
        if ($Value.Kind -eq [DateTimeKind]::Unspecified) {
            return [DateTime]::SpecifyKind($Value, [DateTimeKind]::Utc).Ticks
        }
        return $Value.ToUniversalTime().Ticks
    }
    if ($Value -isnot [string] -or [string]::IsNullOrWhiteSpace($Value)) { return $null }
    $parsed = [DateTimeOffset]::MinValue
    $styles = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
    if ([DateTimeOffset]::TryParse($Value, [Globalization.CultureInfo]::InvariantCulture, $styles, [ref]$parsed)) {
        return $parsed.UtcDateTime.Ticks
    }
    return $null
}

function Test-CellLensIdentity {
    param($Expected, [string]$PythonExecutable, [string]$Module)
    if (-not $Expected -or -not $Expected.pid -or -not $Expected.command_line) { return $false }
    try { $expectedPid = [int]$Expected.pid } catch { return $false }
    if ($expectedPid -le 0) { return $false }
    $current = Get-CellLensIdentity -ProcessId $expectedPid
    if (-not $current) { return $false }
    $expectedCreated = ConvertTo-CellLensUtcTicks -Value $Expected.created_at
    $currentCreated = ConvertTo-CellLensUtcTicks -Value $current.created_at
    if ($null -eq $expectedCreated -or $null -eq $currentCreated) { return $false }
    return $current.pid -eq $expectedPid -and $currentCreated -eq $expectedCreated -and `
        $current.command_line -ceq $Expected.command_line -and `
        $current.command_line.IndexOf($PythonExecutable, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and `
        $current.command_line -match ('(?i)(?:^|\s)-m\s+' + [regex]::Escape($Module) + '(?:\s|$)')
}

function Get-CellLensProcessTree {
    param([int]$ProcessId)
    $rootProcess = Get-CellLensIdentity -ProcessId $ProcessId
    if (-not $rootProcess) { return @() }
    $items = [System.Collections.Generic.List[object]]::new()
    $items.Add($rootProcess)
    for ($index = 0; $index -lt $items.Count; $index++) {
        $parentId = $items[$index].pid
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $parentId" -ErrorAction SilentlyContinue
        foreach ($child in $children) {
            $identity = Get-CellLensIdentity -ProcessId $child.ProcessId
            if ($identity -and $identity.pid -notin $items.pid) { $items.Add($identity) }
        }
    }
    return $items.ToArray()
}

function Stop-CellLensProcessTree {
    [CmdletBinding(SupportsShouldProcess)]
    param($Expected, [string]$PythonExecutable, [string]$Module)
    $current = Get-CellLensIdentity -ProcessId $Expected.pid
    if (-not $current) { return }
    if (-not (Test-CellLensIdentity -Expected $Expected -PythonExecutable $PythonExecutable -Module $Module)) {
        throw "PID $($Expected.pid) no longer matches this workspace service; it was not stopped."
    }
    $members = @(Get-CellLensProcessTree -ProcessId $Expected.pid)
    [array]::Reverse($members)
    foreach ($member in $members) {
        $live = Get-CellLensIdentity -ProcessId $member.pid
        $liveCreated = if ($live) { ConvertTo-CellLensUtcTicks -Value $live.created_at } else { $null }
        $memberCreated = ConvertTo-CellLensUtcTicks -Value $member.created_at
        if ($live -and $null -ne $liveCreated -and $null -ne $memberCreated -and
            $live.pid -eq $member.pid -and $liveCreated -eq $memberCreated -and
            $live.command_line -ceq $member.command_line) {
            if ($PSCmdlet.ShouldProcess("PID $($member.pid)", 'Stop verified CellLens service process')) {
                try { Stop-Process -Id $member.pid -Force -ErrorAction Stop }
                catch {
                    if (Get-CellLensIdentity -ProcessId $member.pid) { throw }
                }
            }
        }
    }
}
