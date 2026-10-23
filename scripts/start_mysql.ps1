param(
    [string]$MysqlExecutable = $env:CELLLENS_MYSQL_EXECUTABLE,
    [string]$DataDirectory = $env:CELLLENS_MYSQL_DATA_DIRECTORY
)
$ErrorActionPreference = "Stop"

if (-not $MysqlExecutable) {
    $detected = Get-Command mysqld.exe -ErrorAction SilentlyContinue
    if ($detected) { $MysqlExecutable = $detected.Source }
    elseif (Test-Path -LiteralPath 'D:\Mysql\mysql-9.2.0-winx64\bin\mysqld.exe') {
        $MysqlExecutable = 'D:\Mysql\mysql-9.2.0-winx64\bin\mysqld.exe'
    }
}
if (-not $DataDirectory -and (Test-Path -LiteralPath 'D:\Mysql\celllens-data')) {
    $DataDirectory = 'D:\Mysql\celllens-data'
}

if (Get-NetTCPConnection -LocalPort 3307 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "CellLens MySQL is already listening on 127.0.0.1:3307"
    exit 0
}
if (-not $MysqlExecutable -or -not (Test-Path -LiteralPath $MysqlExecutable -PathType Leaf)) {
    throw 'Set CELLLENS_MYSQL_EXECUTABLE to mysqld.exe, or start the Docker database first (see README).'
}
if (-not $DataDirectory -or -not (Test-Path -LiteralPath $DataDirectory -PathType Container)) {
    throw 'Set CELLLENS_MYSQL_DATA_DIRECTORY to an initialized project database directory, or use Docker (see README).'
}

$mysqlArguments = @(
    ('--datadir="{0}"' -f $DataDirectory)
    "--port=3307"
    "--bind-address=127.0.0.1"
    "--mysqlx-port=33070"
    "--server-id=3307"
    ('--log-error="{0}\celllens-mysql.err"' -f $DataDirectory)
)
Start-Process -FilePath $mysqlExecutable -ArgumentList $mysqlArguments -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 500
    $listener = Get-NetTCPConnection -LocalPort 3307 -State Listen -ErrorAction SilentlyContinue
} until ($listener -or (Get-Date) -gt $deadline)
if (-not $listener) {
    throw "CellLens MySQL did not start; inspect $dataDirectory\celllens-mysql.err"
}
Write-Host "CellLens MySQL is ready on 127.0.0.1:3307"
