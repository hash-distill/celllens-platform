param([switch]$Apply)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$report = Join-Path $root 'reports/k562-control-cleanup-2026-10-23'
$planPath = Join-Path $report 'confirmed-plan.json'
$plan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
if ($plan.root -ne $root) { throw 'Cleanup plan belongs to a different workspace' }
$targets = @()
foreach ($relative in $plan.paths) {
    if ($relative -notmatch '^(data/raw/replogle-k562/control\.h5ad|data/demo/K562/ALDOA|data/derived/(runs|comparisons)/run_[A-Za-z0-9_]+|data/derived/measured/measured_[a-f0-9]{24}|data/derived/comparison_states/run_[A-Za-z0-9_]+\.json)$') {
        throw "Unapproved deletion target: $relative"
    }
    $target = [System.IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $target.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Deletion target escaped the workspace'
    }
    if (Test-Path -LiteralPath $target) {
        $item = Get-Item -LiteralPath $target -Force
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Deletion target is a filesystem link' }
        if ($item.PSIsContainer) {
            $links = @(Get-ChildItem -LiteralPath $target -Force -Recurse | Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint })
            if ($links.Count) { throw 'Deletion target contains filesystem links' }
        }
    }
    $targets += $target
}
$oldControl = Join-Path $root 'data/raw/replogle-k562/control.h5ad'
if ((Test-Path -LiteralPath $oldControl) -and (Get-FileHash -LiteralPath $oldControl -Algorithm SHA256).Hash.ToLowerInvariant() -ne $plan.old_control_sha256) {
    throw 'Historical control file no longer matches the approved identity'
}
if (-not $Apply) {
    Write-Output 'Preview only. Use -Apply to remove the listed historical inputs, results and database rows.'
    $targets
    exit 0
}
$python = Join-Path $root '.venv/Scripts/python.exe'
Push-Location -LiteralPath $root
try {
    @'
from sqlalchemy import select
from backend.app.config import Settings
from backend.app.container import build_container
from backend.app.db.models import RunModel, MeasuredAnalysisModel
container = build_container(Settings())
with container.store.session_factory() as session:
    runs = list(session.scalars(select(RunModel.status)))
    measured = list(session.scalars(select(MeasuredAnalysisModel.status)))
    if any(status not in {'completed', 'failed'} for status in runs):
        raise RuntimeError('Active predictions exist; cleanup refused')
    if any(status not in {'completed', 'failed', 'cancelled', 'interrupted'} for status in measured):
        raise RuntimeError('Active measured analyses exist; cleanup refused')
'@ | & $python -
    if ($LASTEXITCODE -ne 0) { throw 'Active-job preflight failed' }
    $listener = Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue
    if ($listener) {
        $server = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess)
        $executable = (Resolve-Path -LiteralPath (Join-Path $root '.venv/Scripts/uvicorn.exe')).Path
        if (-not $server.CommandLine.Contains($executable) -or -not $server.CommandLine.Contains('backend.app.main:app') -or -not $server.CommandLine.Contains('--port 8001')) {
            throw 'Port 8001 does not belong to this project API'
        }
        Stop-Process -Id $server.ProcessId -ErrorAction Stop
        Start-Sleep -Seconds 2
    }
    if (Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue) { throw 'API is still running' }
    @'
import json
import os
from pathlib import Path
from sqlalchemy import delete, select
from backend.app.config import Settings
from backend.app.container import build_container
from backend.app.db.models import RunCacheModel, RunArtifactModel, RunAttemptModel, RunEventModel, RunModel, MeasuredAnalysisModel
root = Path('.').resolve()
report = root / 'reports/k562-control-cleanup-2026-10-23'
plan = json.loads((report / 'confirmed-plan.json').read_text(encoding='utf-8'))
if str(root) != plan['root']:
    raise RuntimeError('Cleanup workspace mismatch')
container = build_container(Settings())
tables = [RunCacheModel, RunArtifactModel, RunAttemptModel, RunEventModel, RunModel, MeasuredAnalysisModel]
counts = {}
with container.store.session_factory.begin() as session:
    runs = list(session.scalars(select(RunModel).with_for_update()))
    measured = list(session.scalars(select(MeasuredAnalysisModel).with_for_update()))
    if any(row.status not in {'completed', 'failed'} for row in runs):
        raise RuntimeError('Active prediction detected')
    if any(row.status not in {'completed', 'failed', 'cancelled', 'interrupted'} for row in measured):
        raise RuntimeError('Active measured analysis detected')
    for rows, identifiers, key in [(runs, plan['run_ids'], 'run_id'), (measured, plan['measured_ids'], 'id')]:
        if any(row.cell_line != 'K562' for row in rows if getattr(row, key) in identifiers):
            raise RuntimeError('Cleanup would affect another cell background')
    snapshots = {}
    for model in tables:
        rows = [dict(row) for row in session.execute(select(model.__table__).with_for_update()).mappings()]
        key = 'id' if model is MeasuredAnalysisModel else 'run_id'
        identifiers = plan['measured_ids'] if model is MeasuredAnalysisModel else plan['run_ids']
        snapshots[model.__tablename__] = {'deleted': [row for row in rows if row[key] in identifiers], 'preserved': [row for row in rows if row[key] not in identifiers]}
    backup = report / 'database-before.json'
    if not backup.exists():
        with backup.open('x', encoding='utf-8') as target:
            json.dump({'tables': snapshots, 'scope': 'Historical K562 records only; no expression matrix backup'}, target, ensure_ascii=False, indent=2, default=lambda value: value.isoformat())
            target.flush()
            os.fsync(target.fileno())
    for model in tables:
        key = model.id if model is MeasuredAnalysisModel else model.run_id
        identifiers = plan['measured_ids'] if model is MeasuredAnalysisModel else plan['run_ids']
        counts[model.__tablename__] = session.execute(delete(model).where(key.in_(identifiers))).rowcount
(report / 'database-deleted.json').write_text(json.dumps(counts, indent=2) + '\n', encoding='utf-8')
print(json.dumps(counts))
'@ | & $python -
    if ($LASTEXITCODE -ne 0) { throw 'Database cleanup failed; filesystem targets were not removed' }
    foreach ($target in $targets) {
        if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction Stop }
    }
    foreach ($target in $targets) {
        if (Test-Path -LiteralPath $target) { throw "Deletion incomplete: $target" }
    }
    @'
import hashlib
import json
from pathlib import Path
from backend.app.core.run_manifest import atomic_write_json
from scripts.prepare_k562_control_1024 import prepare_subset
root = Path('.').resolve()
report = root / 'reports/k562-control-cleanup-2026-10-23'
plan = json.loads((report / 'confirmed-plan.json').read_text(encoding='utf-8'))
path = root / 'data/registry/datasets.json'
document = json.loads(path.read_text(encoding='utf-8'))
document['datasets'] = [row for row in document['datasets'] if row['id'] != plan['old_dataset_id']]
atomic_write_json(path, document)
prepare_subset(root)
for relative, expected in plan['preserved_hashes'].items():
    with (root / relative).open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != expected:
            raise RuntimeError(f'Unrelated file changed: {relative}')
result = {'deleted_targets': len(plan['paths']), 'preserved_files_verified': len(plan['preserved_hashes']), 'active_k562_control_cells': 1024}
atomic_write_json(report / 'completed.json', result)
print(json.dumps(result))
'@ | & $python -
    if ($LASTEXITCODE -ne 0) { throw 'Post-cleanup verification failed' }
    Write-Output 'Cleanup complete. Restart with: pwsh -NoProfile -File .\scripts\start_system.ps1 -ApiPort 8001 -StartLocalMysql -SkipBuild'
} finally {
    Pop-Location
}
