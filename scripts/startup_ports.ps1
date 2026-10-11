function Assert-StartupPortAvailable {
    param(
        [Parameter(Mandatory = $true)][string]$Address,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$Service
    )
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {
        $_.LocalPort -eq $Port -and (
            $Address -eq '0.0.0.0' -or $_.LocalAddress -in @($Address, '0.0.0.0', '::')
        )
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
