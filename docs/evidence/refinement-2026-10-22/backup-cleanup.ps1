param([string]$Workspace = 'D:\全球校园人工智能精英大赛', [string]$Backup = 'C:\Users\zhs14\AppData\Local\Temp\celllens-refinement-before-20261022-202509')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $Workspace).Path.TrimEnd('\')
$backupRoot = (Resolve-Path -LiteralPath $Backup).Path
if ($backupRoot.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Backup must be outside workspace' }
$targets = @('.tmp_extract', '.tmp_mysql_check', '.review-2026-10-19', '.celllens-cleanup-20261020', '.frontend-integration-backup-20261020_231120', 'celllens-platform\celllens-review-pdf-vtawrhqt', 'celllens-platform\celllens-review-u09pbrxh', 'celllens-platform\frontend\public\assets\virtual-response-preview-20261022', 'celllens-platform\frontend\src\views\DemoView.vue', 'celllens-platform\frontend\src\components\response\ResponseWorkspace.vue', 'celllens-platform\scripts\build_virtual_response_preview.py', 'celllens-platform\docs\plans\2026-10-22-virtual-cell-positioning-proposal.md', 'celllens-platform\docs\plans\2026-10-22-interactive-cell-view-design.md')
$archivePath = Join-Path $backupRoot 'obsolete-files.zip'
if (Test-Path -LiteralPath $archivePath) { throw 'Refuse to overwrite backup' }
Add-Type -AssemblyName System.IO.Compression
$archive = [IO.Compression.ZipFile]::Open($archivePath, [IO.Compression.ZipArchiveMode]::Create)
$manifest = [Collections.Generic.List[object]]::new()
try {
    foreach ($relative in $targets) {
        $path = [IO.Path]::GetFullPath((Join-Path $root $relative))
        if (-not $path.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Outside workspace: $path" }
        $item = Get-Item -LiteralPath $path -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point: $path" }
        $files = if ($item.PSIsContainer) { @(Get-ChildItem -LiteralPath $path -Recurse -File -Force) } else { @($item) }
        foreach ($file in $files) {
            if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse file: $($file.FullName)" }
            $name = $file.FullName.Substring($root.Length + 1).Replace('\', '/')
            $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file.FullName, $name, [IO.Compression.CompressionLevel]::Fastest)
            $manifest.Add([pscustomobject]@{path=$file.FullName; archive_entry=$name; bytes=$file.Length; sha256=$hash})
        }
    }
} finally { $archive.Dispose() }
$archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    foreach ($row in $manifest) {
        $entry = $archive.GetEntry($row.archive_entry)
        if ($null -eq $entry -or $entry.Length -ne $row.bytes) { throw "Archive missing or wrong size: $($row.path)" }
        $stream = $entry.Open(); $hasher = [Security.Cryptography.SHA256]::Create()
        try { $digest = [Convert]::ToHexString($hasher.ComputeHash($stream)).ToLowerInvariant() } finally { $hasher.Dispose(); $stream.Dispose() }
        if ($digest -ne $row.sha256) { throw "Archive hash mismatch: $($row.path)" }
    }
} finally { $archive.Dispose() }
$result = [ordered]@{workspace=$root; backup=$archivePath; verified=$true; targets=$targets; file_count=$manifest.Count; bytes=($manifest | Measure-Object bytes -Sum).Sum; files=$manifest}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $backupRoot 'obsolete-manifest.json') -Encoding utf8
Write-Output "Verified backup: $($manifest.Count) files, $archivePath"
