function Assert-StartupPortAvailable {
    param(
        [Parameter(Mandatory = $true)][string]$Address,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$Service
    )
    $listeners = @(Get-NetTCPConnection -ErrorAction Stop | Where-Object {
        $_.LocalPort -eq $Port -and (
            $Address -eq '0.0.0.0' -or $_.LocalAddress -in @($Address, '0.0.0.0', '::')
        ) -and $_.State -in @('Listen', 'Bound', 'Established')
    })
    if ($listeners.Count -eq 0) { return }
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        $ownerProcess = Get-Process -Id $_ -ErrorAction SilentlyContinue
        "PID $_ ($($ownerProcess.ProcessName))"
    }) -join ', '
    $guidance = if ($Service -eq 'API') {
        "If CellLens is already running, open http://127.0.0.1:$Port/workbench. To restart, stop its original terminal with Ctrl+C, then rerun this script. Alternatively choose a free -ApiPort."
    } else {
        'Stop the existing frontend or choose a free -FrontendPort.'
    }
    throw "[PORT_IN_USE] $Service port $Port on $Address is occupied by $owners. $guidance"
}

function Get-EnvironmentOverride {
    # Settings load .env, but a same-named shell variable wins silently. Report the
    # override before launch so "已启用/未启用" in the status page is explainable.
    param([Parameter(Mandatory = $true)][string[]]$Name)
    @($Name | Where-Object { $null -ne [Environment]::GetEnvironmentVariable($_, 'Process') })
}

function Assert-NoWorkerOverride {
    $names = @('CELLLENS_WORKER_ENABLED', 'CELLLENS_GPU_AVAILABLE')
    $overrides = @(Get-EnvironmentOverride -Name $names)
    foreach ($name in $overrides) {
        Write-Warning "$name=$([Environment]::GetEnvironmentVariable($name, 'Process')) is set in this shell and overrides .env."
    }
    if ($overrides.Count -gt 0) {
        throw ('[ENV_OVERRIDE] ' + ($overrides -join ', ') +
            ' would override .env for this launch. Clear them first (Remove-Item Env:CELLLENS_WORKER_ENABLED, Env:CELLLENS_GPU_AVAILABLE) or use a fresh terminal.')
    }
}
