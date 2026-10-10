"""Add explicit synthetic single-cell projections without replacing historical results."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.config import get_settings
from backend.app.core.projection import validate_projection
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.core.storage import RunStore
from backend.app.services.demo_projection import write_demo_projection


def supplement(root: Path) -> dict:
    path = root / "projection.json"
    if path.exists():
        validate_projection(path)
        return {"directory": str(root), "action": "already_complete"}
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    if not any("SYNTHETIC" in warning.upper() for warning in summary.get("warnings", [])):
        raise ValueError(f"Refusing synthetic supplementation of non-synthetic results: {root}")
    original_files = {p.name: file_sha256(p) for p in root.iterdir() if p.is_file()}
    write_demo_projection(root, original_manifest_sha256=original_files["manifest.json"])
    for name, digest in original_files.items():
        if file_sha256(root / name) != digest:
            raise ValueError(f"Original artifact changed: {root / name}")
    additions = {
        name: {"sha256": file_sha256(root / name), "size_bytes": (root / name).stat().st_size}
        for name in ["demo_cells.npz", "projection.json"]
    }
    atomic_write_json(
        root / "projection_provenance.json",
        {
            "version": 1,
            "data_kind": "synthetic_demo",
            "created_at": datetime.now(UTC).isoformat(),
            "reason": "Add synthetic single-cell demonstration inputs and projection to legacy demo results",
            "original_files": original_files,
            "added_files": additions,
            "warning": "New synthetic samples, not recovered original cells or STATE predictions.",
        },
    )
    return {
        "directory": str(root),
        "action": "supplemented",
        "original_files": original_files,
        "added_files": additions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Write additions and register projection artifacts"
    )
    args = parser.parse_args()
    settings = get_settings()
    store = RunStore(settings.database_url)
    results = []
    try:
        records, total = store.list_runs(limit=100, offset=0, status="completed", mode="precomputed")
        for offset in range(100, total, 100):
            batch, _ = store.list_runs(limit=100, offset=offset, status="completed", mode="precomputed")
            records.extend(batch)
        for root in sorted(settings.demo_root.glob("*/*")):
            if not (root / "summary.json").is_file():
                continue
            if not args.apply:
                results.append(
                    {"directory": str(root), "missing_projection": not (root / "projection.json").is_file()}
                )
                continue
            result = supplement(root)
            if result["action"] == "supplemented":
                manifest_path = root / "manifest.json"
                backup_root = settings.project_root / "reports/projection-repair/backups"
                backup_root.mkdir(parents=True, exist_ok=True)
                digest = file_sha256(manifest_path)
                (backup_root / f"bundle-manifest-{digest}.json").write_bytes(manifest_path.read_bytes())
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for name in ["projection.json", "demo_cells.npz", "projection_provenance.json"]:
                    manifest["files"][name] = file_sha256(root / name)
                atomic_write_json(manifest_path, manifest)
            results.append(result)
        for record in records:
            root = settings.derived_root / record.run_id
            if not args.apply:
                results.append(
                    {"run_id": record.run_id, "missing_projection": not (root / "projection.json").is_file()}
                )
                continue
            result = supplement(root)
            known = {artifact.relative_path for artifact in store.artifacts(record.run_id)}
            for name, kind, mime in [
                ("projection.json", "projection", "application/json"),
                ("demo_cells.npz", "demo_cells", "application/octet-stream"),
                ("projection_provenance.json", "projection_provenance", "application/json"),
            ]:
                path = root / name
                relative = f"{record.run_id}/{name}"
                if path.is_file() and relative not in known:
                    store.register_artifact(
                        record.run_id, kind, relative, file_sha256(path), path.stat().st_size, mime
                    )
            result["run_id"] = record.run_id
            results.append(result)
        output = settings.project_root / "reports/projection-repair"
        output.mkdir(parents=True, exist_ok=True)
        atomic_write_json(output / ("applied.json" if args.apply else "inventory.json"), {"items": results})
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
