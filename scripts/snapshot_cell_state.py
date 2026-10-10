"""Preserve the existing scientific outputs before a read-only view change."""

import json
import shutil
from pathlib import Path

from backend.app.core.run_manifest import file_sha256

root = Path(__file__).resolve().parents[1]
report = root / "reports/scientific-cell-state-2026-10-09"
report.mkdir(parents=True, exist_ok=True)
baseline = report / "baseline.json"
if not baseline.exists():
    paths = sorted((root / "data/derived/runs").rglob("*"))
    baseline.write_text(
        json.dumps({str(p.relative_to(root)): file_sha256(p) for p in paths if p.is_file()}, indent=2),
        encoding="utf-8",
    )
    for name in (
        "backend/app/api/runs.py",
        "frontend/src/views/WorkbenchView.vue",
        "frontend/src/components/tabs/CellStateTab.vue",
        "frontend/src/api/client.ts",
        "frontend/src/components/function/FunctionWorkspace.vue",
        "frontend/src/components/response/ResponseWorkspace.vue",
        "pyproject.toml",
    ):
        target = report / "before" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
else:
    document = json.loads(baseline.read_text(encoding="utf-8"))
    changed = [name for name, sha in document.items() if file_sha256(root / name) != sha]
    print(json.dumps({"files": len(document), "changed": changed}))
