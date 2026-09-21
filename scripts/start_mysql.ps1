$ErrorActionPreference = "Stop"

$mysqlExecutable = "D:\Mysql\mysql-9.2.0-winx64\bin\mysqld.exe"
$dataDirectory = "D:\Mysql\celllens-data"

if (Get-NetTCPConnection -LocalPort 3307 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "CellLens MySQL is already listening on 127.0.0.1:3307"
    exit 0
}
if (-not (Test-Path -LiteralPath $mysqlExecutable -PathType Leaf)) {
    throw "MySQL executable not found: $mysqlExecutable"
}
if (-not (Test-Path -LiteralPath $dataDirectory -PathType Container)) {
    throw "CellLens MySQL data directory not found: $dataDirectory"
}

$mysqlArguments = @(
    "--datadir=$dataDirectory"
    "--port=3307"
    "--bind-address=127.0.0.1"
    "--mysqlx-port=33070"
    "--server-id=3307"
    "--log-error=$dataDirectory\celllens-mysql.err"
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
