"""Explicit CPU-only preparation for existing completed real runs; no prediction."""

import argparse
import json
import time
from pathlib import Path

from backend.app.config import Settings
from backend.app.container import build_container
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.schemas import RunStatus
from backend.app.services.cell_state_preparation import prepare_cell_state_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--all-completed", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.run_id) == args.all_completed:
        parser.error("Choose --run-id or --all-completed")
    container = build_container(Settings(worker_enabled=False))
    ids = args.run_id
    if args.all_completed:
        rows, total = container.store.list_runs(limit=100, offset=0, status="completed", mode="online")
        ids = [r.run_id for r in rows]
        for offset in range(100, total, 100):
            rows, _ = container.store.list_runs(limit=100, offset=offset, status="completed", mode="online")
            ids.extend(r.run_id for r in rows)
    report = {"operation": "CPU-only existing-run figure preparation", "runs": []}
    for run_id in ids:
        started = time.perf_counter()
        row = {"run_id": run_id}
        try:
            if container.store.get(run_id).status != RunStatus.COMPLETED:
                raise ValueError("Only completed runs can be backfilled")
            root = container.settings.derived_root / run_id
            # Originals stay untouched. Only a new, separately registered directory is added.
            original = {p.name: file_sha256(p) for p in root.iterdir() if p.is_file()}
            with container.store.named_lock(f"celllens:figures:{run_id}", timeout_seconds=7200):
                manifest = prepare_cell_state_artifacts(container, run_id)
            if any(file_sha256(root / name) != sha for name, sha in original.items()):
                raise ValueError("Original run artifacts changed during preparation")
            row.update(
                status="prepared", figures=len(manifest["figures"]),
                unavailable=manifest["unavailable"], original_files_verified=len(original),
                added_bytes=sum(p.stat().st_size for p in (root / "cell_state").iterdir()),
            )
        except Exception as exc:
            row.update(status="failed", error=str(exc))
        row["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        report["runs"].append(row)
        atomic_write_json(args.report, report)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    if any(r["status"] == "failed" for r in report["runs"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
